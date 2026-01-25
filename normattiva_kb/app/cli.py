from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import re
from loguru import logger
from sqlalchemy import text
import uvicorn
from lxml import etree

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.db import repo, models
from app.ingestion.scanner import scan_inputs
from app.ingestion.zip_cache import extract_zip_to_cache
from app.ingestion.raw_store import raw_file_record
from app.ingestion.normattiva_reader import read_xml
from app.parsing.normattiva_parser import parse_normattiva, parse_normattiva_iter
from app.parsing.akoma_parser import AkomaNtosoParser
from app.parsing.akoma_models import DocumentOut
from app.parsing.quality import quality_metrics
from app.parsing.references import extract_references
from app.parsing.urn_resolver import UrnResolver
from app.parsing.canonicalize import canonical_node
from app.parsing.hierarchy_builder import build_sort_key
from app.parsing.node_text import clean_text
from app.core.utils_ids import canonical_doc_id, sha256_text
from app.analysis.conflict_detector import detect_temporal_conflicts, ConflictCandidate
from app.api.main import app as fastapi_app



def cmd_ingest(input_dir: str) -> None:
    with SessionLocal() as session:
        run = models.IngestionRun(input_dir=input_dir, status="running")
        session.add(run)
        session.flush()

        files = scan_inputs(input_dir)
        stats = {"files": len(files), "xml": 0, "zip": 0}

        for path in files:
            if path.suffix.lower() == ".zip":
                stats["zip"] += 1
                cache_dir = Path(get_settings().cache_dir)
                extracted = extract_zip_to_cache(path, cache_dir)
                raw = repo.upsert_raw_file(session, raw_file_record(path))
                for xml_path in extracted:
                    data = raw_file_record(xml_path, derived_from=raw.raw_id, is_from_zip=True)
                    repo.upsert_raw_file(session, data)
            else:
                stats["xml"] += 1
                repo.upsert_raw_file(session, raw_file_record(path))

        run.status = "finished"
        run.finished_at = dt.datetime.utcnow()
        run.stats_json = stats
        session.commit()
        logger.info("ingest_complete", stats=stats)


def cmd_parse() -> None:
    import sys

    sys.setrecursionlimit(5000)
    with SessionLocal() as session:
        raw_files = session.query(models.RawFile).filter(models.RawFile.status == "new").all()
        for raw in raw_files:
            try:
                with session.begin():
                    path = Path(raw.original_path)
                    size = path.stat().st_size
                    if size > 50_000_000:
                        root_tag = _detect_root_tag(path)
                        is_akoma = "akoma" in root_tag
                        if is_akoma:
                            parser = AkomaNtosoParser()
                            akoma_doc = parser.parse_iter(str(path))
                            parsed = _map_akoma_output(akoma_doc, path)
                        else:
                            parsed = parse_normattiva_iter(path)
                    else:
                        tree = read_xml(path)
                        root_tag = tree.getroot().tag.lower()
                        is_akoma = "akoma" in root_tag
                        if is_akoma:
                            parser = AkomaNtosoParser()
                            akoma_doc = parser.parse(tree)
                            parsed = _map_akoma_output(akoma_doc, path)
                        else:
                            parsed = parse_normattiva(tree)
                    doc_info = parsed["doc"]
                    doc_id = sha256_text(doc_info["canonical_doc"])
                    doc_payload = {
                        "doc_id": doc_id,
                        "canonical_doc": doc_info["canonical_doc"],
                        "doc_type": doc_info["doc_type"],
                        "number": doc_info["number"],
                        "year": doc_info["year"],
                        "title": doc_info["title"],
                        "last_seen_raw_id": raw.raw_id,
                    }
                    doc = repo.upsert_document(session, doc_payload)

                    version_tag = doc_info.get("version_tag") or f"import:{raw.raw_id}"
                    text_concat = "\n".join(node["text_raw"] for node in parsed["nodes"])
                    checksum = sha256_text(text_concat)
                    existing_version = session.query(models.DocumentVersion).filter(
                        models.DocumentVersion.doc_id == doc.doc_id,
                        models.DocumentVersion.version_tag == version_tag,
                    ).first()
                    if existing_version and existing_version.checksum_text == checksum:
                        raw.status = "parsed"
                        continue
                    if existing_version and existing_version.checksum_text != checksum:
                        raw.status = "conflict"
                        raw.error = "checksum_mismatch_for_version"
                        continue

                    version_payload = {
                        "doc_id": doc.doc_id,
                        "version_tag": version_tag,
                        "checksum_text": checksum,
                        "source_raw_id": raw.raw_id,
                        "valid_from": doc_info.get("valid_from"),
                        "valid_to": doc_info.get("valid_to"),
                        "metadata_json": {},
                    }
                    version = repo.upsert_document_version(session, version_payload)

                    is_current = version.valid_to is None
                    buffer: list[models.Node] = []
                    for node in parsed["nodes"]:
                        node_payload = {
                            "node_id": sha256_text(f"{doc.doc_id}:{version.version_id}:{node['canonical_path']}"),
                            "doc_id": doc.doc_id,
                            "version_id": version.version_id,
                            "node_type": node["node_type"],
                            "label": node["label"],
                            "canonical_path": node["canonical_path"],
                            "hierarchy_string": node.get("hierarchy_string"),
                            "sort_key": node["sort_key"],
                            "ordinal": None,
                            "heading": node.get("heading"),
                            "text_raw": node["text_raw"],
                            "text_clean": node["text_clean"],
                            "text_hash": node["text_hash"],
                            "flags_json": {},
                            "metadata_json": node.get("metadata_json", {}),
                            "valid_from": version.valid_from,
                            "valid_to": version.valid_to,
                            "is_current_law": is_current,
                            "source_url": node.get("source_url"),
                        }
                        buffer.append(models.Node(**node_payload))
                        if len(buffer) >= 2000:
                            session.bulk_save_objects(buffer)
                            buffer.clear()
                    if buffer:
                        session.bulk_save_objects(buffer)

                    raw.status = "parsed"
            except Exception as exc:
                raw.status = "error"
                raw.error = str(exc)
        session.commit()
        logger.info("parse_complete", count=len(raw_files))


def cmd_build_fts() -> None:
    with SessionLocal() as session:
        session.execute(
            text("CREATE INDEX IF NOT EXISTS idx_nodes_text_clean ON nodes USING GIN (to_tsvector('italian', text_clean));")
        )
        session.commit()
        logger.info("fts_ready")


def cmd_extract_references() -> None:
    with SessionLocal() as session:
        nodes = session.query(models.Node).all()
        for node in nodes:
            doc = session.get(models.Document, node.doc_id)
            resolver = UrnResolver(doc.canonical_doc if doc else None)
            refs = extract_references(node.text_clean)
            for ref in refs:
                existing = session.query(models.ReferenceExtracted).filter(
                    models.ReferenceExtracted.source_node_id == node.node_id,
                    models.ReferenceExtracted.match_text == ref.get("match_text", ""),
                ).first()
                if existing:
                    continue
                target_doc = ref.get("target_canonical_doc")
                target_node = None
                if target_doc and ref.get("target_article"):
                    target_node = canonical_node(
                        target_doc,
                        ref.get("target_article"),
                        ref.get("target_comma"),
                        ref.get("target_letter"),
                        ref.get("target_number"),
                    )
                resolved_urn, confidence_score, method = resolver.resolve(
                    ref.get("match_text", ""),
                    ref.get("raw_snippet", ""),
                )
                session.add(
                    models.UrnResolutionLog(
                        original_text=ref.get("match_text", ""),
                        resolved_urn=resolved_urn,
                        confidence_score=confidence_score,
                        resolution_method=method,
                        document_id=node.doc_id,
                    )
                )
                extracted = models.ReferenceExtracted(
                    source_node_id=node.node_id,
                    raw_snippet=ref.get("raw_snippet", node.text_clean[:400]),
                    match_text=ref.get("match_text", ""),
                    relation_type=ref.get("relation_type", "CITES"),
                    target_canonical_doc=target_doc or resolved_urn,
                    target_article=ref.get("target_article"),
                    target_comma=ref.get("target_comma"),
                    target_letter=ref.get("target_letter"),
                    target_number=ref.get("target_number"),
                    target_canonical_node=target_node,
                    confidence=ref.get("confidence", 0.4),
                    method=ref.get("method", "regex:v1"),
                )
                session.add(extracted)
        session.commit()
        logger.info("references_extracted")


def cmd_resolve_references() -> None:
    with SessionLocal() as session:
        refs = session.query(models.ReferenceExtracted).all()
        for ref in refs:
            target_node_id = None
            if ref.target_canonical_node:
                target_node = session.query(models.Node).filter(
                    models.Node.canonical_path == ref.target_canonical_node.split("#")[-1]
                ).first()
                if target_node:
                    target_node_id = target_node.node_id
            resolved = models.ReferenceResolved(
                source_node_id=ref.source_node_id,
                target_node_id=target_node_id,
                target_canonical_node=ref.target_canonical_node or "",
                relation_type=ref.relation_type,
                confidence=ref.confidence,
            )
            session.merge(resolved)
        session.commit()
        logger.info("references_resolved")


def cmd_stats() -> None:
    with SessionLocal() as session:
        nodes = session.query(models.Node).all()
        metrics = quality_metrics([{"node_type": n.node_type, "text_clean": n.text_clean} for n in nodes])
        logger.info("stats", metrics=metrics)


def cmd_detect_conflicts() -> None:
    with SessionLocal() as session:
        nodes = (
            session.query(models.Node)
            .order_by(models.Node.doc_id, models.Node.canonical_path, models.Node.valid_from)
            .yield_per(1000)
        )
        candidates = detect_temporal_conflicts(nodes)
        created = 0
        for candidate in candidates:
            normalized = _normalize_candidate(candidate)
            existing = (
                session.query(models.ConflictEvent)
                .filter(
                    models.ConflictEvent.node_id_a == normalized.node_id_a,
                    models.ConflictEvent.node_id_b == normalized.node_id_b,
                )
                .first()
            )
            if existing:
                continue
            session.add(
                models.ConflictEvent(
                    doc_id=normalized.doc_id,
                    canonical_path=normalized.canonical_path,
                    node_id_a=normalized.node_id_a,
                    node_id_b=normalized.node_id_b,
                    version_id_a=normalized.version_id_a,
                    version_id_b=normalized.version_id_b,
                    valid_from_a=normalized.valid_from_a,
                    valid_to_a=normalized.valid_to_a,
                    valid_from_b=normalized.valid_from_b,
                    valid_to_b=normalized.valid_to_b,
                    severity=normalized.severity,
                    status="pending",
                )
            )
            created += 1
        session.commit()
        logger.info("conflicts_detected", created=created)


def _normalize_candidate(candidate: ConflictCandidate) -> ConflictCandidate:
    if candidate.node_id_a <= candidate.node_id_b:
        return candidate
    return ConflictCandidate(
        doc_id=candidate.doc_id,
        canonical_path=candidate.canonical_path,
        node_id_a=candidate.node_id_b,
        node_id_b=candidate.node_id_a,
        version_id_a=candidate.version_id_b,
        version_id_b=candidate.version_id_a,
        valid_from_a=candidate.valid_from_b,
        valid_to_a=candidate.valid_to_b,
        valid_from_b=candidate.valid_from_a,
        valid_to_b=candidate.valid_to_a,
        severity=candidate.severity,
    )


def _map_akoma_output(doc: DocumentOut, path: Path | None = None) -> dict:
    doc_type, number, year = _parse_akoma_urn(doc.urn)
    if doc.urn:
        canonical_doc = doc.urn.split("/")[-1]
    elif path:
        canonical_doc = path.stem
    else:
        canonical_doc = canonical_doc_id(doc_type, number, year)
    nodes: list[dict] = []
    for node in doc.nodes:
        canonical_path = node.canonical_path
        node_type = canonical_path.split("/")[-1].split(":")[0]
        text_raw = node.text_content
        text_cleaned = clean_text(text_raw)
        nodes.append(
            {
                "node_type": node_type,
                "label": canonical_path.split("/")[-1],
                "canonical_path": canonical_path,
                "hierarchy_string": canonical_path.replace("/", " > "),
                "sort_key": build_sort_key(canonical_path),
                "heading": None,
                "text_raw": text_raw,
                "text_clean": text_cleaned,
                "text_hash": sha256_text(text_cleaned),
                "metadata_json": {
                    "references": [ref.model_dump() for ref in node.references],
                },
            }
        )
    return {
        "doc": {
            "canonical_doc": canonical_doc,
            "doc_type": doc_type,
            "number": int(number) if number and str(number).isdigit() else None,
            "year": int(year) if year and str(year).isdigit() else None,
            "title": None,
            "valid_from": None,
            "valid_to": None,
            "version_tag": doc.expression_urn or (f"v:{path.name}" if path else doc.version_date),
        },
        "nodes": nodes,
    }


def _parse_akoma_urn(urn: str | None) -> tuple[str, str | None, str | None]:
    if not urn:
        return "altro", None, None
    match = re.search(r"([a-z-]+):(\d{4})-\d{2}-\d{2};(\d+)", urn)
    if not match:
        match = re.search(r"([a-z-]+):(\d{4});(\d+)", urn)
    if not match:
        return "altro", None, None
    doc_type, year, number = match.groups()
    return doc_type, number, year


def _detect_root_tag(path: Path) -> str:
    context = etree.iterparse(str(path), events=("start",), recover=True, huge_tree=True)
    for _event, elem in context:
        return elem.tag.lower()
    return ""


def cmd_serve() -> None:
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normattiva KB CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--dir", required=True)
    sub.add_parser("parse")
    sub.add_parser("build-fts")
    sub.add_parser("extract-references")
    sub.add_parser("resolve-references")
    sub.add_parser("stats")
    sub.add_parser("detect-conflicts")
    sub.add_parser("serve")
    return parser


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "ingest":
        cmd_ingest(args.dir)
    elif args.command == "parse":
        cmd_parse()
    elif args.command == "build-fts":
        cmd_build_fts()
    elif args.command == "extract-references":
        cmd_extract_references()
    elif args.command == "resolve-references":
        cmd_resolve_references()
    elif args.command == "stats":
        cmd_stats()
    elif args.command == "detect-conflicts":
        cmd_detect_conflicts()
    elif args.command == "serve":
        cmd_serve()


if __name__ == "__main__":
    main()
