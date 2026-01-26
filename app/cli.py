# app/cli.py
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import uvicorn
from loguru import logger
from lxml import etree
from sqlalchemy import func, text

from app.api.main import app as fastapi_app
from app.analysis.conflict_detector import ConflictCandidate, detect_temporal_conflicts
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.utils_ids import sha256_text
from app.core.utils_text import text_hash as compute_text_hash
from app.db import models, repo
from app.db.session import SessionLocal
from app.ingestion.normattiva_reader import read_xml
from app.ingestion.raw_store import raw_file_record
from app.ingestion.scanner import scan_inputs
from app.ingestion.zip_cache import extract_zip_to_cache
from app.parsing.akoma_models import DocumentOut
from app.parsing.akoma_parser import AkomaNtosoParser
from app.parsing.canonicalize import canonical_node
from app.parsing.hierarchy_builder import build_sort_key
from app.parsing.node_text import clean_text
from app.parsing.normattiva_parser import parse_normattiva, parse_normattiva_iter
from app.parsing.quality import quality_metrics
from app.parsing.references import extract_references
from app.parsing.urn_resolver import UrnResolver


# ----------------------------
# COMANDI CLI
# ----------------------------

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
                raw_zip = repo.upsert_raw_file(session, raw_file_record(path))
                for xml_path in extracted:
                    data = raw_file_record(xml_path, derived_from=raw_zip.raw_id, is_from_zip=True)
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
    sys.setrecursionlimit(5000)

    with SessionLocal() as session:
        raw_ids = [
            rid
            for (rid,) in (
                session.query(models.RawFile.raw_id)
                .filter(models.RawFile.status == "new")
                .order_by(models.RawFile.raw_id.asc())
                .all()
            )
        ]

    logger.info("parse_start", count=len(raw_ids))

    processed = 0
    for raw_id in raw_ids:
        processed += 1
        session = SessionLocal()
        path = None  # evita UnboundLocalError
        try:
            raw = session.get(models.RawFile, raw_id)
            if not raw:
                session.close()
                continue

            path = Path(raw.original_path)
            parsed = _parse_one_file(path)
            _persist_parsed(session, raw, parsed)
            session.commit()
            logger.info("parse_ok", file=path.name, raw_id=raw_id)

        except Exception as exc:
            session.rollback()
            err = str(exc)
            file_label = str(path) if path else f"raw_id:{raw_id}"
            logger.exception("parse_fail", file=file_label, raw_id=raw_id, error=err)

            try:
                raw_db = session.get(models.RawFile, raw_id)
                if raw_db:
                    raw_db.status = "error"
                    raw_db.error = err
                    session.commit()
            except Exception:
                pass
        finally:
            session.close()

    logger.info("parse_complete", processed=processed)


def cmd_build_fts() -> None:
    with SessionLocal() as session:
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_nodes_text_clean "
                "ON nodes USING GIN (to_tsvector('italian', text_clean));"
            )
        )
        session.commit()
        logger.info("fts_ready")


def cmd_extract_references() -> None:
    with SessionLocal() as session:
        nodes_q = session.query(models.Node).order_by(models.Node.doc_id).yield_per(500)
        created = 0

        for node in nodes_q:
            doc = session.get(models.Document, node.doc_id)
            resolver = UrnResolver(doc.canonical_doc if doc else None)

            refs = extract_references(node.text_clean or "")
            if not refs:
                continue

            for ref in refs:
                match_text = ref.get("match_text", "")
                if not match_text:
                    continue

                relation_type = ref.get("relation_type", "CITES")

                existing = (
                    session.query(models.ReferenceExtracted)
                    .filter(
                        models.ReferenceExtracted.source_node_id == node.node_id,
                        models.ReferenceExtracted.match_text == match_text,
                        models.ReferenceExtracted.relation_type == relation_type,
                    )
                    .first()
                )
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
                    match_text, ref.get("raw_snippet", "")
                )

                session.add(
                    models.UrnResolutionLog(
                        original_text=match_text,
                        resolved_urn=resolved_urn,
                        confidence_score=confidence_score,
                        resolution_method=method,
                        document_id=node.doc_id,
                    )
                )

                session.add(
                    models.ReferenceExtracted(
                        source_node_id=node.node_id,
                        raw_snippet=ref.get("raw_snippet", "Snippet non disponibile"),
                        match_text=match_text,
                        relation_type=relation_type,
                        target_canonical_doc=target_doc or resolved_urn,
                        target_article=ref.get("target_article"),
                        target_canonical_node=target_node,
                        confidence=ref.get("confidence", 0.4),
                        method=ref.get("method", "regex:v1"),
                    )
                )
                created += 1

        session.commit()
        logger.info("references_extracted", created=created)


def cmd_resolve_references() -> None:
    with SessionLocal() as session:
        logger.info("Caricamento riferimenti in memoria...")
        all_refs = session.query(models.ReferenceExtracted).all()
        logger.info(f"Caricati {len(all_refs)} riferimenti.")

        resolved_count = 0
        seen_keys: set[tuple[str, str, str]] = set()

        for ref in all_refs:
            target_str = (ref.target_canonical_node or ref.target_canonical_doc or "").strip()
            target_node_id = None

            if target_str:
                candidate_path = target_str.split("#", 1)[-1] if "#" in target_str else target_str
                candidate_path = candidate_path.strip()

                target_node = (
                    session.query(models.Node)
                    .filter(models.Node.canonical_path == candidate_path)
                    .first()
                )
                if target_node:
                    target_node_id = target_node.node_id

            if not target_node_id and not target_str:
                continue

            key = (ref.source_node_id, target_str, ref.relation_type)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            session.merge(
                models.ReferenceResolved(
                    source_node_id=ref.source_node_id,
                    target_node_id=target_node_id,
                    target_canonical_node=target_str,
                    relation_type=ref.relation_type,
                    confidence=ref.confidence,
                )
            )
            resolved_count += 1

            if resolved_count % 1000 == 0:
                session.commit()

        session.commit()
        logger.info("references_resolved", processed=resolved_count)


def cmd_stats() -> None:
    with SessionLocal() as session:
        nodes_q = session.query(models.Node).limit(10000)
        items = [{"node_type": n.node_type, "text_clean": n.text_clean} for n in nodes_q]
        metrics = quality_metrics(items)
        logger.info("stats", metrics=metrics)


def cmd_detect_conflicts() -> None:
    with SessionLocal() as session:
        nodes = (
            session.query(models.Node)
            .order_by(models.Node.doc_id, models.Node.canonical_path)
            .yield_per(1000)
        )
        candidates = detect_temporal_conflicts(nodes)

        created = 0
        for cand in candidates:
            norm = _normalize_candidate(cand)
            existing = (
                session.query(models.ConflictEvent)
                .filter(
                    models.ConflictEvent.node_id_a == norm.node_id_a,
                    models.ConflictEvent.node_id_b == norm.node_id_b,
                )
                .first()
            )
            if existing:
                continue

            session.add(
                models.ConflictEvent(
                    doc_id=norm.doc_id,
                    canonical_path=norm.canonical_path,
                    node_id_a=norm.node_id_a,
                    node_id_b=norm.node_id_b,
                    version_id_a=norm.version_id_a,
                    version_id_b=norm.version_id_b,
                    severity=norm.severity,
                    status="pending",
                )
            )
            created += 1

        session.commit()
        logger.info("conflicts_detected", created=created)


def cmd_serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn.run(fastapi_app, host=host, port=port)


def cmd_preview_rag(count: int = 3) -> None:
    with SessionLocal() as session:
        nodes = (
            session.query(models.Node)
            .filter(func.length(models.Node.text_clean) > 50)
            .order_by(func.random())
            .limit(count)
            .all()
        )

        print(f"\n🧠 PREVIEW RAG: {len(nodes)} Nodi Casuali\n" + "=" * 60)
        for i, node in enumerate(nodes, 1):
            doc = session.get(models.Document, node.doc_id)
            doc_title = doc.title if doc and doc.title else "Titolo sconosciuto"
            print(f"📄 [{i}] DOCUMENTO: {doc_title} ({doc.canonical_doc if doc else '?'})")
            print(f"📍 POSIZIONE: {node.hierarchy_string or 'N/A'}")
            print(f"🔗 PATH: {node.canonical_path}")
            print(f"📝 CONTENUTO:\n{(node.text_clean or '')[:200]}...")
            print("-" * 60)


def cmd_backfill_hierarchy(batch: int = 5000, limit: int | None = None) -> None:
    """
    Riempie hierarchy_string per i nodi già presenti (NULL o vuoto),
    senza rifare parse e senza toccare node_id.
    """
    logger.info("backfill_hierarchy_start", batch=batch, limit=limit)

    with SessionLocal() as session:
        q = (
            session.query(models.Node.node_id)
            .filter(
                (models.Node.hierarchy_string.is_(None)) | (models.Node.hierarchy_string == "")
            )
            .order_by(models.Node.node_id.asc())
        )
        if limit is not None:
            q = q.limit(limit)

        pending: list[str] = []
        updated_total = 0

        for (node_id,) in q.yield_per(batch):
            pending.append(node_id)
            if len(pending) >= batch:
                updated_total += _backfill_chunk(pending)
                pending.clear()

        if pending:
            updated_total += _backfill_chunk(pending)

    logger.info("backfill_hierarchy_done", updated=updated_total)


def _backfill_chunk(node_ids: list[str]) -> int:
    with SessionLocal() as session:
        nodes = session.query(models.Node).filter(models.Node.node_id.in_(node_ids)).all()
        if not nodes:
            return 0

        doc_ids = {n.doc_id for n in nodes}
        docs = session.query(models.Document.doc_id, models.Document.canonical_doc).filter(
            models.Document.doc_id.in_(doc_ids)
        ).all()
        doc_map = {d[0]: d[1] for d in docs}

        updated = 0
        for n in nodes:
            if n.hierarchy_string:
                continue
            n.hierarchy_string = _compute_hierarchy_string(doc_map.get(n.doc_id), n.canonical_path)
            if n.hierarchy_string:
                updated += 1

        session.commit()
        return updated


# ----------------------------
# HELPERS
# ----------------------------

def _compute_hierarchy_string(doc_canonical: str | None, canonical_path: str | None) -> str | None:
    if not canonical_path:
        return None

    parts = [p for p in canonical_path.strip("/").split("/") if p]
    if not parts:
        return None

    # rimuove solo prefissi tecnici comuni
    skip_keywords = {"akomantoso", "akomanotoso", "akoma", "akn", "it", "act", "main", "main.xml"}
    cleaned_parts = [p for p in parts if p.lower() not in skip_keywords]
    if not cleaned_parts:
        cleaned_parts = parts  # fallback: non scartare tutto

    def pretty(seg: str) -> str:
        base, _, rest = seg.partition(":")
        b = base.lower().strip()
        r = rest.strip()

        if b in ("art", "articolo", "article"):
            return f"Art. {r}" if r else "Art."
        if b in ("com", "comma", "paragraph"):
            return f"Comma {r}" if r else "Comma"
        if b in ("let", "lett", "letter", "lettera"):
            return f"lett. {r}" if r else "Lettera"
        if b in ("num", "numero", "item", "number"):
            return f"n. {r}" if r else "Numero"
        if b in ("capo", "chapter"):
            return f"Capo {r}" if r else "Capo"
        if b in ("tit", "titolo", "title"):
            return f"Titolo {r}" if r else "Titolo"
        if r:
            return f"{b} {r}"
        return b

    chain = " > ".join(pretty(p) for p in cleaned_parts)
    return chain


def _parse_one_file(path: Path) -> dict:
    size = path.stat().st_size
    root_tag = _detect_root_tag(path)
    is_akoma = "akoma" in root_tag or "akomantoso" in root_tag

    if size > 50_000_000:
        if is_akoma:
            return _map_akoma_output(AkomaNtosoParser().parse_iter(str(path)), path)
        return parse_normattiva_iter(path)

    tree = read_xml(path)
    if is_akoma:
        return _map_akoma_output(AkomaNtosoParser().parse(tree), path)
    return parse_normattiva(tree)


def _persist_parsed(session, raw: models.RawFile, parsed: dict) -> None:
    path = Path(raw.original_path)
    doc_info = parsed["doc"]
    doc_id = sha256_text(doc_info["canonical_doc"])

    doc = repo.upsert_document(
        session,
        {
            "doc_id": doc_id,
            "canonical_doc": doc_info["canonical_doc"],
            "doc_type": doc_info["doc_type"],
            "number": doc_info["number"],
            "year": doc_info["year"],
            "title": doc_info.get("title") or path.stem,
            "last_seen_raw_id": raw.raw_id,
        },
    )

    text_concat = "\n".join(node.get("text_raw", "") for node in parsed["nodes"])
    checksum = sha256_text(text_concat)
    version_tag = doc_info.get("version_tag") or f"import:{raw.raw_id}"

    version = repo.upsert_document_version(
        session,
        {
            "doc_id": doc.doc_id,
            "version_tag": version_tag,
            "checksum_text": checksum,
            "source_raw_id": raw.raw_id,
            "valid_from": doc_info.get("valid_from"),
            "valid_to": doc_info.get("valid_to"),
            "metadata_json": doc_info.get("metadata_json", {}),
        },
    )

    nodes_to_insert = []
    for node_data in parsed["nodes"]:
        cp = node_data["canonical_path"]

        # text_hash sempre presente
        source_text = node_data.get("text_clean") or node_data.get("text_raw") or ""
        text_hash_value = node_data.get("text_hash") or compute_text_hash(source_text)

        # ⚠️ ID STABILE (come in origine): non includere text_hash qui
        node_id = sha256_text(f"{doc.doc_id}:{version.version_id}:{cp}")

        hierarchy_str = node_data.get("hierarchy_string")
        if not hierarchy_str:
            hierarchy_str = _compute_hierarchy_string(doc.canonical_doc, cp)

        node_obj = models.Node(
            node_id=node_id,
            doc_id=doc.doc_id,
            version_id=version.version_id,
            node_type=node_data["node_type"],
            label=node_data.get("label") or cp.split("/")[-1],
            canonical_path=cp,
            sort_key=node_data.get("sort_key") or build_sort_key(cp),
            text_raw=node_data.get("text_raw", ""),
            text_clean=node_data.get("text_clean", ""),
            text_hash=text_hash_value,
            is_current_law=(version.valid_to is None),
            hierarchy_string=hierarchy_str,
            heading=node_data.get("heading"),
            source_url=node_data.get("source_url"),
            metadata_json=node_data.get("metadata_json", {}),
        )

        nodes_to_insert.append(node_obj)

        if len(nodes_to_insert) >= 1000:
            session.add_all(nodes_to_insert)
            session.flush()
            nodes_to_insert.clear()

    if nodes_to_insert:
        session.add_all(nodes_to_insert)
        session.flush()

    raw.status = "parsed"


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
        severity=candidate.severity,
    )


def _map_akoma_output(doc: DocumentOut, path: Path | None = None) -> dict:
    doc_type, number, year = _parse_akoma_urn(doc.urn)
    canonical_doc = doc.urn.split("/")[-1] if doc.urn else (path.stem if path else "doc")

    nodes = []
    for node in doc.nodes:
        text_raw = node.text_content or ""
        text_clean = clean_text(text_raw)
        nodes.append(
            {
                "node_type": node.canonical_path.split("/")[-1].split(":")[0],
                "canonical_path": node.canonical_path,
                "sort_key": build_sort_key(node.canonical_path),
                "text_raw": text_raw,
                "text_clean": text_clean,
                "text_hash": compute_text_hash(text_clean),
                "hierarchy_string": None,  # fallback nel persist
            }
        )

    return {
        "doc": {
            "canonical_doc": canonical_doc,
            "doc_type": doc_type,
            "number": number,
            "year": year,
            "version_tag": doc.expression_urn,
        },
        "nodes": nodes,
    }


def _parse_akoma_urn(urn: str | None) -> tuple[str, str | None, str | None]:
    if not urn:
        return "altro", None, None
    m = re.search(r"([a-z-]+):(\d{4})[^\d]*;(\d+)", urn)
    return m.groups() if m else ("altro", None, None)


def _detect_root_tag(path: Path) -> str:
    try:
        context = etree.iterparse(str(path), events=("start",))
        for _, elem in context:
            return (elem.tag or "").lower()
    except Exception:
        return ""
    return ""


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

    preview = sub.add_parser("preview-rag")
    preview.add_argument("--count", type=int, default=3)

    backfill = sub.add_parser("backfill-hierarchy")
    backfill.add_argument("--batch", type=int, default=5000)
    backfill.add_argument("--limit", type=int, default=None)

    return parser


def main() -> None:
    configure_logging(get_settings().log_level)
    args = build_parser().parse_args()

    cmds = {
        "ingest": lambda: cmd_ingest(args.dir),
        "parse": cmd_parse,
        "build-fts": cmd_build_fts,
        "extract-references": cmd_extract_references,
        "resolve-references": cmd_resolve_references,
        "stats": cmd_stats,
        "detect-conflicts": cmd_detect_conflicts,
        "serve": lambda: cmd_serve(),
        "preview-rag": lambda: cmd_preview_rag(args.count),
        "backfill-hierarchy": lambda: cmd_backfill_hierarchy(batch=args.batch, limit=args.limit),
    }
    cmds[args.command]()


if __name__ == "__main__":
    main()
