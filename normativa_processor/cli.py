from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
import json
import importlib
import importlib.util

from normativa_processor.chunking.chunker import split_into_chunks
from normativa_processor.chunking.validator import validate_chunks
from normativa_processor.core.cache import PDFProcessorCache
from normativa_processor.core.config import Config, ProcessingConfig
from normativa_processor.core.exceptions import PDFExtractionError, ValidationError
from normativa_processor.core.models import ArticleSection
from normativa_processor.core.types import NLPModelType
from normativa_processor.extraction.pdf_extractor import extract_text_pdf
from normativa_processor.extraction.text_cleaner import normalize_text
from normativa_processor.parsing.hierarchy_parser import parse_hierarchy
from normativa_processor.parsing.metadata_parser import (
    build_metadata,
    detect_title,
    extract_doc_citation,
    normalize_dates,
)

spacy = importlib.import_module("spacy") if importlib.util.find_spec("spacy") else None


def load_spacy_model() -> NLPModelType:
    if spacy is None:
        return None
    try:
        return spacy.load("it_core_news_sm")
    except Exception as exc:
        logging.warning("Impossibile caricare spaCy: %s", exc)
        return None


def write_json(output_path: Path, data: dict) -> None:
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_xml(output_path: Path, data: dict) -> None:
    root = ET.Element("document")
    metadata_el = ET.SubElement(root, "document_metadata")
    for key, value in data["document_metadata"].items():
        child = ET.SubElement(metadata_el, key)
        child.text = "" if value is None else str(value)

    chunks_el = ET.SubElement(root, "chunks")
    for chunk in data["chunks"]:
        chunk_el = ET.SubElement(chunks_el, "chunk")
        for key, value in chunk.items():
            child = ET.SubElement(chunk_el, key)
            if isinstance(value, list):
                for item in value:
                    item_el = ET.SubElement(child, "item")
                    item_el.text = str(item)
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    sub_el = ET.SubElement(child, sub_key)
                    sub_el.text = str(sub_value)
            else:
                child.text = "" if value is None else str(value)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def log_stats(chunks: list[dict]) -> None:
    if not chunks:
        return
    avg_tokens = sum(c["token_estimate"] for c in chunks) / len(chunks)
    with_refs = sum(1 for c in chunks if c["reform_references"])
    logging.info("Chunk totali: %s", len(chunks))
    logging.info("Token medi: %.1f", avg_tokens)
    logging.info("Chunk con riferimenti normativi: %.1f%%", (with_refs / len(chunks)) * 100)


def build_output(
    source_filename: str,
    text: str,
    total_pages: int,
    chunks: list[dict],
    tables: list[list[str]],
    warnings: list[str],
    nlp: NLPModelType,
) -> dict:
    metadata = build_metadata(source_filename, text, total_pages, len(chunks), nlp, warnings)
    metadata["norm_citations"] = sorted({ref for chunk in chunks for ref in chunk["reform_references"]})
    if tables:
        metadata["tables_detected"] = len(tables)
    return {"document_metadata": metadata, "chunks": chunks}


def process_pdf_data(
    path: Path,
    output_format: str,
    use_ocr: bool,
    config: ProcessingConfig,
    summary_strategy: str,
) -> Optional[dict]:
    try:
        raw_text, total_pages, tables = extract_text_pdf(path, use_ocr)
    except PDFExtractionError as exc:
        logging.error("Errore estrazione %s: %s", path.name, exc)
        return None

    nlp = load_spacy_model()
    cleaned_text = normalize_text(raw_text)
    cleaned_text = normalize_dates(cleaned_text, nlp)
    sections, warnings = parse_hierarchy(cleaned_text, nlp)

    title = detect_title(cleaned_text, path.stem)
    context = {"title": title, "doc_citation": extract_doc_citation(title), "nlp": nlp}
    doc_slug = re_slug(path.name)

    chunks: list[dict] = []
    for section in sections:
        chunks.extend(split_into_chunks(section, doc_slug, context, config, summary_strategy))

    if tables:
        table_section = ArticleSection(
            article_id="Tabelle",
            section_title="Tabelle estratte",
            hierarchy=["Allegati"],
            text="\n".join("\n".join(lines) for lines in tables),
            is_annex=True,
        )
        chunks.extend(split_into_chunks(table_section, doc_slug, context, config, summary_strategy))

    try:
        chunks = validate_chunks(chunks, cleaned_text, config)
    except Exception as exc:
        raise ValidationError(str(exc)) from exc

    log_stats(chunks)
    return build_output(path.name, cleaned_text, total_pages, chunks, tables, warnings, nlp)


def process_pdf(path: Path, output_folder: Path, output_format: str, use_ocr: bool, config: ProcessingConfig, summary_strategy: str) -> None:
    output_suffix = "json" if output_format == "json" else "xml"
    output_path = output_folder / f"{path.stem}_cleaned.{output_suffix}"
    if output_path.exists():
        logging.info("File già pulito: skipped (%s)", path.name)
        return

    output = process_pdf_data(path, output_format, use_ocr, config, summary_strategy)
    if output is None:
        return

    output_folder.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        write_json(output_path, output)
    else:
        write_xml(output_path, output)
    logging.info("Output salvato: %s", output_path)


def iter_pdf_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return list(folder.glob(pattern))


def re_slug(filename: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "_", Path(filename).stem.lower()).strip("_")


def process_folder_parallel(
    input_folder: str,
    output_folder: str,
    output_format: str,
    recursive: bool,
    use_ocr: bool,
    config: ProcessingConfig,
    cache: Optional[PDFProcessorCache],
    summary_strategy: str,
    max_workers: int,
) -> dict[str, bool]:
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    pdf_files = iter_pdf_files(input_path, recursive)
    results: dict[str, bool] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for pdf_path in pdf_files:
            if cache:
                cached = cache.get(pdf_path)
                if cached:
                    logging.info("Cache hit: %s", pdf_path.name)
                    output_file = output_path / f"{pdf_path.stem}_cleaned.{output_format}"
                    if output_format == "json":
                        write_json(output_file, cached)
                    else:
                        write_xml(output_file, cached)
                    results[str(pdf_path)] = True
                    continue

            futures[executor.submit(process_pdf_data, pdf_path, output_format, use_ocr, config, summary_strategy)] = pdf_path

        for future in as_completed(futures):
            pdf_path = futures[future]
            try:
                result = future.result()
                if result is None:
                    results[str(pdf_path)] = False
                    continue
                if cache:
                    cache.set(pdf_path, result)
                output_file = Path(output_folder) / f"{pdf_path.stem}_cleaned.{output_format}"
                if output_format == "json":
                    write_json(output_file, result)
                else:
                    write_xml(output_file, result)
                results[str(pdf_path)] = True
            except Exception as exc:
                logging.error("Errore processing %s: %s", pdf_path.name, exc)
                results[str(pdf_path)] = False

    return results


def process_folder(
    input_folder: str,
    output_folder: str,
    output_format: str = "json",
    recursive: bool = False,
    use_ocr: bool = False,
    config: Optional[ProcessingConfig] = None,
    summary_strategy: str = "keyword",
) -> None:
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    config = config or ProcessingConfig()

    if not input_path.exists():
        raise FileNotFoundError(f"Cartella input non trovata: {input_folder}")

    cache = None
    if Config.get("cache.enabled", False):
        cache_dir = Path(Config.get("cache.directory", ".cache/normativa"))
        cache = PDFProcessorCache(cache_dir)

    if Config.get("parallel.enabled", False):
        max_workers = int(Config.get("parallel.max_workers", 4))
        process_folder_parallel(
            input_folder,
            output_folder,
            output_format,
            recursive,
            use_ocr,
            config,
            cache,
            summary_strategy,
            max_workers,
        )
        return

    for pdf_path in iter_pdf_files(input_path, recursive):
        process_pdf(pdf_path, output_path, output_format, use_ocr, config, summary_strategy)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Processa PDF normativi per RAG.")
    parser.add_argument("--input_folder", required=True, help="Cartella contenente PDF")
    parser.add_argument("--output_folder", required=True, help="Cartella output")
    parser.add_argument("--format", choices=["json", "xml"], default="json")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--ocr", action="store_true", help="Usa OCR se possibile")
    parser.add_argument("--quiet", action="store_true", help="Riduci logging")
    parser.add_argument("--config", help="Percorso YAML/JSON con configurazione opzionale")
    return parser


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    Config.load(args.config)
    config = Config.processing_config()
    summary_strategy = Config.get("summarization.strategy", "keyword")
    process_folder(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        output_format=args.format,
        recursive=args.recursive,
        use_ocr=args.ocr,
        config=config,
        summary_strategy=summary_strategy,
    )


if __name__ == "__main__":
    main()
