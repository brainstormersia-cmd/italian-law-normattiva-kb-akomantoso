#!/usr/bin/env python3
"""
Normativa PDF processor for RAG preprocessing (Python 3.12+).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional
from xml.etree import ElementTree as ET


try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fitz = None


LIGATURES = {
    "ﬁ": "fi",
    "ﬀ": "ff",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
}

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
        r"agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]

NORM_TYPE_MAP = {
    "legge": "legge",
    "decreto": "decreto",
    "d.lgs": "decreto",
    "d.l.": "decreto",
    "dpr": "decreto",
    "direttiva": "direttiva UE",
    "regolamento": "regolamento",
    "codice": "codice",
}

TAG_KEYWORDS = {
    "obblighi": ["obbligo", "deve", "devono", "obbligatorio"],
    "divieti": ["vietato", "divieto", "non è consentito", "non possono"],
    "sanzioni": ["sanzione", "sanzioni", "ammenda", "multa", "pena"],
    "privacy": ["dati personali", "privacy", "gdpr", "protezione dei dati"],
    "appalti": ["appalto", "gara", "contraente", "stazione appaltante"],
    "definizioni": ["si intende", "definizione", "ai fini del presente"],
    "deroghe": ["deroga", "in deroga", "fatto salvo"],
    "entrata in vigore": ["entra in vigore", "vigore dal"],
    "competenze": ["competenza", "competenze", "attribuito"],
}

REF_PATTERN = re.compile(
    r"\b(Legge|L\.|D\.Lgs\.|D\.L\.|DPR|Regolamento|Direttiva)\s*"
    r"(\d{1,4})/(\d{4})",
    re.IGNORECASE,
)


@dataclass
class ArticleSection:
    article_id: str
    section_title: str
    hierarchy: list[str]
    text: str


def extract_text_pdf(path: Path) -> tuple[str, int]:
    if pdfplumber is None and fitz is None:
        raise RuntimeError("pdfplumber o PyMuPDF non disponibili.")

    if pdfplumber is not None:
        try:
            with pdfplumber.open(path) as pdf:
                pages_text = []
                headers = []
                footers = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    if lines:
                        headers.append(lines[0])
                        footers.append(lines[-1])
                    pages_text.append(text)
                cleaned = remove_repeated_headers(pages_text, headers, footers)
                return cleaned, len(pdf.pages)
        except Exception as exc:
            logging.warning("pdfplumber fallito per %s: %s", path.name, exc)

    if fitz is not None:
        doc = fitz.open(path)  # type: ignore[call-arg]
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        doc.close()
        return "\n".join(pages_text), len(pages_text)

    raise RuntimeError("Impossibile estrarre testo dal PDF.")


def remove_repeated_headers(
    pages_text: Iterable[str], headers: list[str], footers: list[str]
) -> str:
    header_counts = Counter(headers)
    footer_counts = Counter(footers)
    total_pages = len(headers)
    repeated_headers = {
        h for h, count in header_counts.items() if count >= max(2, int(total_pages * 0.6))
    }
    repeated_footers = {
        f for f, count in footer_counts.items() if count >= max(2, int(total_pages * 0.6))
    }
    cleaned_pages = []
    for text in pages_text:
        lines = [line.strip() for line in text.splitlines()]
        filtered = []
        for line in lines:
            if not line:
                filtered.append("")
                continue
            if line in repeated_headers or line in repeated_footers:
                continue
            if re.fullmatch(r"\d{1,4}", line):
                continue
            if re.search(r"\bBOZZA\b|\bG\.U\.\b", line):
                continue
            filtered.append(line)
        cleaned_pages.append("\n".join(filtered))
    return "\n".join(cleaned_pages)


def normalize_text(text: str) -> str:
    for src, tgt in LIGATURES.items():
        text = text.replace(src, tgt)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def detect_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return fallback


def detect_norm_type(title: str) -> str:
    lowered = title.lower()
    for key, value in NORM_TYPE_MAP.items():
        if key in lowered:
            return value
    return "altro"


def extract_date(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if len(match.groups()) == 3:
            day, month, year = match.groups()
            month_number = month
            if month.isalpha():
                month_number = month_name_to_number(month)
            if month_number.isdigit():
                try:
                    date = dt.date(int(year), int(month_number), int(day))
                    return date.isoformat()
                except ValueError:
                    continue
    return None


def month_name_to_number(month: str) -> str:
    months = {
        "gennaio": "01",
        "febbraio": "02",
        "marzo": "03",
        "aprile": "04",
        "maggio": "05",
        "giugno": "06",
        "luglio": "07",
        "agosto": "08",
        "settembre": "09",
        "ottobre": "10",
        "novembre": "11",
        "dicembre": "12",
    }
    return months.get(month.lower(), "")


def parse_hierarchy(text: str) -> list[ArticleSection]:
    hierarchy: list[str] = []
    sections: list[ArticleSection] = []
    current_article_id = ""
    current_title = ""
    current_lines: list[str] = []

    def flush_article() -> None:
        nonlocal current_article_id, current_title, current_lines
        if current_article_id and current_lines:
            sections.append(
                ArticleSection(
                    article_id=current_article_id,
                    section_title=current_title,
                    hierarchy=list(hierarchy),
                    text="\n".join(current_lines).strip(),
                )
            )
        current_article_id = ""
        current_title = ""
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue

        if re.match(r"^Titolo\s+[IVXLC\d]+", line, re.IGNORECASE):
            flush_article()
            hierarchy = [line]
            continue
        if re.match(r"^Capo\s+[IVXLC\d]+", line, re.IGNORECASE):
            flush_article()
            hierarchy = hierarchy[:1] + [line] if hierarchy else [line]
            continue
        if re.match(r"^Sezione\s+[\w\d\-]+", line, re.IGNORECASE):
            flush_article()
            hierarchy = hierarchy[:2] + [line] if len(hierarchy) >= 2 else hierarchy + [line]
            continue

        article_match = re.match(
            r"^(Articolo|Art\.|Art)\s*(\d+[^\s]*)", line, re.IGNORECASE
        )
        if article_match:
            flush_article()
            current_article_id = f"Art. {article_match.group(2)}"
            current_title = line
            current_lines.append(line)
            continue

        if current_lines:
            current_lines.append(line)
        else:
            current_article_id = "Preambolo"
            current_title = "Preambolo"
            current_lines = [line]

    flush_article()
    return sections


def split_into_chunks(section: ArticleSection, doc_slug: str) -> list[dict]:
    text = section.text
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        if estimate_tokens(current + "\n\n" + para) <= 900:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)

    normalized_chunks: list[str] = []
    for chunk in chunks:
        if estimate_tokens(chunk) > 1500:
            normalized_chunks.extend(split_long_chunk(chunk))
        else:
            normalized_chunks.append(chunk)

    final_chunks: list[dict] = []
    for idx, chunk in enumerate(normalized_chunks, start=1):
        chunk_text = add_overlap(normalized_chunks, idx - 1)
        chunk_text = prepend_hierarchy(section, chunk_text)
        chunk_id = build_chunk_id(doc_slug, section.article_id, idx)
        final_chunks.append(
            {
                "chunk_id": chunk_id,
                "article_id": section.article_id,
                "section_title": section.section_title,
                "parent_hierarchy": section.hierarchy,
                "reform_references": extract_references(chunk_text),
                "effective_date": extract_effective_date(chunk_text),
                "tags": extract_tags(chunk_text),
                "full_chunk_text": chunk_text,
                "summary_50": summarize(chunk_text, 50),
                "summary_150": summarize(chunk_text, 150),
                "token_estimate": estimate_tokens(chunk_text),
            }
        )
    return final_chunks


def add_overlap(chunks: list[str], index: int) -> str:
    chunk = chunks[index]
    if index == 0:
        return chunk
    prev_lines = chunks[index - 1].splitlines()
    overlap_lines = prev_lines[-4:]
    overlap_text = "\n".join(overlap_lines).strip()
    if overlap_text:
        return f"{overlap_text}\n{chunk}"
    return chunk


def prepend_hierarchy(section: ArticleSection, chunk: str) -> str:
    hierarchy_text = " - ".join(section.hierarchy + [section.article_id])
    return f"{hierarchy_text}\n{chunk}".strip()


def split_long_chunk(chunk: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", chunk)
    parts = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if estimate_tokens(current + " " + sentence) <= 900:
            current = f"{current} {sentence}"
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def extract_references(text: str) -> list[str]:
    refs = {f"{match.group(1)} {match.group(2)}/{match.group(3)}" for match in REF_PATTERN.finditer(text)}
    return sorted(refs)


def extract_effective_date(text: str) -> Optional[str]:
    if "entra in vigore" in text.lower():
        return extract_date(text)
    return None


def extract_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)
    if not tags:
        tags = ["normativa", "disposizioni"]
    return tags[:8]


def summarize(text: str, max_words: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    words: list[str] = []
    for sentence in sentences:
        sentence_words = sentence.split()
        if not sentence_words:
            continue
        if len(words) + len(sentence_words) <= max_words:
            words.extend(sentence_words)
        else:
            remaining = max_words - len(words)
            if remaining > 0:
                words.extend(sentence_words[:remaining])
            break
    return " ".join(words)


def build_chunk_id(doc_slug: str, article_id: str, index: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", article_id.lower()).strip("_")
    return f"{doc_slug}_{slug}_{index}"


def document_slug(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", Path(filename).stem.lower()).strip("_")


def validate_chunks(chunks: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for chunk in chunks:
        key = chunk["full_chunk_text"]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


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
) -> dict:
    title = detect_title(text, Path(source_filename).stem)
    metadata = {
        "source_filename": source_filename,
        "title": title,
        "publication_date": extract_date(text),
        "last_amendment_date": extract_date(text),
        "norm_type": detect_norm_type(title),
        "total_pages": total_pages,
        "total_chunks": len(chunks),
        "processed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {"document_metadata": metadata, "chunks": chunks}


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
            else:
                child.text = "" if value is None else str(value)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def process_pdf(path: Path, output_folder: Path, output_format: str) -> None:
    output_suffix = "json" if output_format == "json" else "xml"
    output_path = output_folder / f"{path.stem}_cleaned.{output_suffix}"
    if output_path.exists():
        logging.info("File già pulito: skipped (%s)", path.name)
        return

    try:
        raw_text, total_pages = extract_text_pdf(path)
    except Exception as exc:
        logging.error("Errore estrazione %s: %s", path.name, exc)
        return

    cleaned_text = normalize_text(raw_text)
    sections = parse_hierarchy(cleaned_text)
    doc_slug = document_slug(path.name)

    chunks: list[dict] = []
    for section in sections:
        chunks.extend(split_into_chunks(section, doc_slug))

    chunks = validate_chunks(chunks)
    log_stats(chunks)
    output = build_output(path.name, cleaned_text, total_pages, chunks)

    output_folder.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        write_json(output_path, output)
    else:
        write_xml(output_path, output)

    logging.info("Output salvato: %s", output_path)


def iter_pdf_files(folder: Path, recursive: bool) -> Iterator[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    yield from folder.glob(pattern)


def process_folder(
    input_folder: str,
    output_folder: str,
    output_format: str = "json",
    recursive: bool = False,
) -> None:
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    if not input_path.exists():
        raise FileNotFoundError(f"Cartella input non trovata: {input_folder}")

    for pdf_path in iter_pdf_files(input_path, recursive):
        process_pdf(pdf_path, output_path, output_format)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Processa PDF normativi per RAG.")
    parser.add_argument("--input_folder", required=True, help="Cartella contenente PDF")
    parser.add_argument("--output_folder", required=True, help="Cartella output")
    parser.add_argument("--format", choices=["json", "xml"], default="json")
    parser.add_argument("--recursive", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_cli_parser()
    args = parser.parse_args()
    try:
        process_folder(
            input_folder=args.input_folder,
            output_folder=args.output_folder,
            output_format=args.format,
            recursive=args.recursive,
        )
    except Exception as exc:
        logging.error("Errore: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
