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
from dataclasses import dataclass
import importlib
import importlib.util
from pathlib import Path
from typing import Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

pdfplumber = importlib.import_module("pdfplumber") if importlib.util.find_spec("pdfplumber") else None
fitz = importlib.import_module("fitz") if importlib.util.find_spec("fitz") else None
spacy = importlib.import_module("spacy") if importlib.util.find_spec("spacy") else None
pytesseract = (
    importlib.import_module("pytesseract") if importlib.util.find_spec("pytesseract") else None
)

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
    "diritto del lavoro": ["lavoratore", "datore di lavoro", "lavoro"],
    "tutela ambientale": ["ambiente", "ambientale", "inquinamento"],
}

REF_PATTERN = re.compile(
    r"\b(Legge|L\.|D\.?Lgs\.|D\.?L\.|DPR|Regolamento|Direttiva)\s*"
    r"(\d{1,4})/(\d{4})",
    re.IGNORECASE,
)
REF_ART_PATTERN = re.compile(
    r"\bart\.\s*(\d+[a-z\-]*)\s+(?:del\s+)?"
    r"(Legge|L\.|D\.?Lgs\.|D\.?L\.|DPR|Regolamento|Direttiva)\s*"
    r"(\d{1,4})/(\d{4})",
    re.IGNORECASE,
)

CROSS_REF_PATTERNS = [
    ("modifica", re.compile(r"come modificato da\s+([^\.;\n]+)", re.IGNORECASE)),
    ("sostituzione", re.compile(r"sostituito da\s+([^\.;\n]+)", re.IGNORECASE)),
    ("abrogazione", re.compile(r"abrogato da\s+([^\.;\n]+)", re.IGNORECASE)),
    ("abrogazione", re.compile(r"abrogato dall'?art\.\s*([^\.;\n]+)", re.IGNORECASE)),
    ("rinvio", re.compile(r"ai sensi dell'art\.\s*([^\.;\n]+)", re.IGNORECASE)),
    ("rinvio", re.compile(r"ai sensi dell'articolo\s*([^\.;\n]+)", re.IGNORECASE)),
    ("modifica", re.compile(r"\[(?:modificato|sostituito)\s+da\s+([^\]]+)\]", re.IGNORECASE)),
]

BOILERPLATE_PATTERNS = [
    re.compile(r"Gazzetta Ufficiale\s+n\.\s*\d+\s+del\s+\d{1,2}\s+\w+\s+\d{4}", re.IGNORECASE),
    re.compile(r"Serie Generale", re.IGNORECASE),
    re.compile(r"^Visto il\b", re.IGNORECASE),
    re.compile(r"^Visti\b", re.IGNORECASE),
    re.compile(r"^Considerato che\b", re.IGNORECASE),
    re.compile(r"^Ritenuto\b", re.IGNORECASE),
]

HIERARCHY_PATTERNS = {
    "titolo": re.compile(r"^Titolo\s+[IVXLC\d]+", re.IGNORECASE),
    "capo": re.compile(r"^Capo\s+[IVXLC\d]+", re.IGNORECASE),
    "sezione": re.compile(r"^Sezione\s+[\w\d\-]+", re.IGNORECASE),
    "articolo": re.compile(r"^(Articolo|Art\.|Art)\s*(\d+[\w\-]*)", re.IGNORECASE),
    "comma": re.compile(r"^(Comma|co\.|c\.)\s*(\d+[\w\-]*)", re.IGNORECASE),
    "lettera": re.compile(r"^[a-z]\)", re.IGNORECASE),
    "punto": re.compile(r"^(Punto|Punto\s+|punto\s+)?\d+(\.\d+)*\)", re.IGNORECASE),
    "numero": re.compile(r"^numero\s*\d+", re.IGNORECASE),
    "tabella": re.compile(r"^Tabella\s+\d+", re.IGNORECASE),
    "allegato": re.compile(r"^Allegato\s+[A-Z0-9]+", re.IGNORECASE),
    "annesso": re.compile(r"^Annesso\s+[A-Z0-9IVXLC]+", re.IGNORECASE),
    "disposizioni_finali": re.compile(r"^Disposizioni\s+finali", re.IGNORECASE),
    "abrogazioni": re.compile(r"^Abrogazioni", re.IGNORECASE),
}


@dataclass
class ArticleSection:
    article_id: str
    section_title: str
    hierarchy: list[str]
    text: str
    is_annex: bool = False


def load_spacy_model() -> Optional[object]:
    if spacy is None:
        return None
    try:
        return spacy.load("it_core_news_sm")
    except Exception:
        return None


def extract_text_pdf(path: Path, use_ocr: bool) -> tuple[str, int, list[list[str]]]:
    if pdfplumber is None and fitz is None:
        raise RuntimeError("pdfplumber o PyMuPDF non disponibili.")

    if pdfplumber is not None:
        try:
            with pdfplumber.open(path) as pdf:
                pages_text = []
                headers = []
                footers = []
                tables: list[list[str]] = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    if lines:
                        headers.append(lines[0])
                        footers.append(lines[-1])
                    pages_text.append(text)
                    for table in page.extract_tables() or []:
                        table_md = table_to_markdown(table)
                        if table_md:
                            tables.append(table_md)
                cleaned = remove_repeated_headers(pages_text, headers, footers)
                if use_ocr and not cleaned.strip():
                    cleaned = ocr_pdf(path)
                return cleaned, len(pdf.pages), tables
        except Exception as exc:
            logging.warning("pdfplumber fallito per %s: %s", path.name, exc)

    if fitz is not None:
        doc = fitz.open(path)  # type: ignore[call-arg]
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        doc.close()
        extracted = "\n".join(pages_text)
        if use_ocr and not extracted.strip():
            extracted = ocr_pdf(path)
        return extracted, len(pages_text), []

    raise RuntimeError("Impossibile estrarre testo dal PDF.")


def ocr_pdf(path: Path) -> str:
    if pytesseract is None or fitz is None:
        logging.info("OCR non disponibile, skip.")
        return ""
    logging.info("OCR attivato per %s", path.name)
    doc = fitz.open(path)  # type: ignore[call-arg]
    ocr_text = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        text = pytesseract.image_to_string(img_bytes, lang="ita")
        ocr_text.append(text)
    doc.close()
    return "\n".join(ocr_text)


def table_to_markdown(table: list[list[Optional[str]]]) -> list[str]:
    if not table:
        return []
    clean_rows = []
    for row in table:
        if not row:
            continue
        clean_rows.append([cell.strip() if cell else "" for cell in row])
    if not clean_rows:
        return []
    header = clean_rows[0]
    separator = ["---" for _ in header]
    md_lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(separator) + " |"]
    for row in clean_rows[1:]:
        md_lines.append("| " + " | ".join(row) + " |")
    return md_lines


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


def normalize_text(text: str, nlp: Optional[object]) -> str:
    for src, tgt in LIGATURES.items():
        text = text.replace(src, tgt)
    text = normalize_legal_abbreviations(text)
    text = remove_boilerplate(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = normalize_dates(text, nlp)
    return text.strip()


def normalize_legal_abbreviations(text: str) -> str:
    replacements = {
        "d.lgs.": "D.Lgs.",
        "d.l.": "D.L.",
        "d.p.r.": "DPR",
        "l.": "L.",
    }
    for src, tgt in replacements.items():
        text = re.sub(re.escape(src), tgt, text, flags=re.IGNORECASE)
    return text


def remove_boilerplate(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in BOILERPLATE_PATTERNS):
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_dates(text: str, nlp: Optional[object]) -> str:
    def replace_match(match: re.Match[str]) -> str:
        day, month, year = match.groups()
        month_number = month
        if month.isalpha():
            month_number = month_name_to_number(month)
        if month_number.isdigit():
            try:
                date = dt.date(int(year), int(month_number), int(day))
                return date.isoformat()
            except ValueError:
                return match.group(0)
        return match.group(0)

    for pattern in DATE_PATTERNS:
        text = pattern.sub(replace_match, text)

    if nlp is None:
        return text

    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_.lower() != "date":
            continue
        parsed = parse_ner_date(ent.text)
        if parsed:
            text = text.replace(ent.text, parsed)
    return text


def parse_ner_date(value: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = pattern.search(value)
        if match:
            day, month, year = match.groups()
            month_number = month_name_to_number(month) if month.isalpha() else month
            if month_number.isdigit():
                try:
                    date = dt.date(int(year), int(month_number), int(day))
                    return date.isoformat()
                except ValueError:
                    return None
    return None


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
    dates = extract_dates(text)
    return dates[0] if dates else None


def extract_dates(text: str, nlp: Optional[object] = None) -> list[str]:
    dates: set[str] = set()
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            day, month, year = match.groups()
            month_number = month_name_to_number(month) if month.isalpha() else month
            if month_number.isdigit():
                try:
                    date = dt.date(int(year), int(month_number), int(day))
                    dates.add(date.isoformat())
                except ValueError:
                    continue
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_.lower() == "date":
                parsed = parse_ner_date(ent.text)
                if parsed:
                    dates.add(parsed)
    return sorted(dates)


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


def parse_hierarchy(text: str, nlp: Optional[object]) -> tuple[list[ArticleSection], list[str]]:
    stack: list[str] = []
    sections: list[ArticleSection] = []
    current_article_id = ""
    current_title = ""
    current_lines: list[str] = []
    warnings: list[str] = []
    current_is_annex = False

    def flush_article() -> None:
        nonlocal current_article_id, current_title, current_lines, current_is_annex
        if current_article_id and current_lines:
            sections.append(
                ArticleSection(
                    article_id=current_article_id,
                    section_title=current_title,
                    hierarchy=list(stack),
                    text="\n".join(current_lines).strip(),
                    is_annex=current_is_annex,
                )
            )
        current_article_id = ""
        current_title = ""
        current_lines = []
        current_is_annex = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue

        matched = False
        for level, pattern in HIERARCHY_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue
            matched = True
            if level in {"titolo", "capo", "sezione", "disposizioni_finali", "abrogazioni"}:
                flush_article()
                stack = adjust_stack(stack, level, line)
            elif level in {"allegato", "annesso", "tabella"}:
                flush_article()
                stack = adjust_stack(stack, level, line)
                current_is_annex = True
                current_article_id = line
                current_title = line
                current_lines.append(line)
            elif level == "articolo":
                flush_article()
                current_article_id = f"Art. {match.group(2)}"
                current_title = line
                current_lines.append(line)
            elif level in {"comma", "lettera", "punto", "numero"}:
                if current_article_id:
                    current_lines.append(line)
                else:
                    current_article_id = "Preambolo"
                    current_title = "Preambolo"
                    current_lines = [line]
            break

        if matched:
            continue

        if current_lines:
            current_lines.append(line)
        else:
            current_article_id = "Preambolo"
            current_title = "Preambolo"
            current_lines = [line]

    flush_article()
    if not sections:
        warnings.append("Possibile allegato non parsificato")

    if nlp is not None:
        for section in sections:
            if "Art." not in section.article_id and "Articolo" in section.section_title:
                warnings.append(f"Sezione ambigua: {section.section_title}")
    return sections, warnings


def adjust_stack(stack: list[str], level: str, line: str) -> list[str]:
    order = [
        "titolo",
        "capo",
        "sezione",
        "disposizioni_finali",
        "abrogazioni",
        "allegato",
        "annesso",
        "tabella",
    ]
    if level not in order:
        return stack
    idx = order.index(level)
    new_stack = stack[:idx]
    new_stack.append(line)
    return new_stack


def split_into_chunks(
    section: ArticleSection,
    doc_slug: str,
    context: dict,
) -> list[dict]:
    text = section.text
    units = split_by_subsections(text)
    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
            continue
        if estimate_tokens(current + "\n\n" + unit) <= 800:
            current = f"{current}\n\n{unit}"
        else:
            chunks.append(current)
            current = unit
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
        subsection = extract_subsection_label(chunk_text)
        citation_key = build_citation_key(section, context, subsection)
        chunk_text = prepend_context(section, chunk_text, citation_key)
        reform_refs = extract_references(chunk_text)
        cross_refs = extract_cross_references(chunk_text)
        tags = extract_tags(chunk_text, context.get("nlp"))
        summary_50 = summarize(chunk_text, citation_key, 50, tags)
        summary_150 = summarize(chunk_text, citation_key, 150, tags)
        token_est = estimate_tokens_precise(chunk_text)
        rag_fields = build_rag_fields(
            citation_key,
            tags,
            summary_50,
            summary_150,
            context,
            reform_refs,
            cross_refs,
            extract_effective_date(chunk_text),
        )

        final_chunks.append(
            {
                "chunk_id": build_chunk_id(doc_slug, section.article_id, idx),
                "citation_key": citation_key,
                "article_id": section.article_id,
                "section_title": section.section_title,
                "parent_hierarchy": section.hierarchy,
                "reform_references": reform_refs,
                "cross_references": cross_refs,
                "effective_date": extract_effective_date(chunk_text),
                "tags": tags,
                "full_chunk_text": chunk_text,
                "summary_50": summary_50,
                "summary_150": summary_150,
                "token_estimate": token_est,
                "rag_optimized_fields": rag_fields,
            }
        )
    return final_chunks


def split_by_subsections(text: str) -> list[str]:
    lines = text.splitlines()
    units: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            current.append("")
            continue
        if is_subsection_marker(stripped) and current:
            units.append("\n".join(current).strip())
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        units.append("\n".join(current).strip())
    if not units:
        return [text]
    return units


def is_subsection_marker(line: str) -> bool:
    markers = [
        HIERARCHY_PATTERNS["comma"],
        HIERARCHY_PATTERNS["lettera"],
        HIERARCHY_PATTERNS["punto"],
        HIERARCHY_PATTERNS["numero"],
    ]
    return any(pattern.match(line) for pattern in markers)


def extract_subsection_label(text: str) -> Optional[str]:
    for line in text.splitlines():
        if HIERARCHY_PATTERNS["comma"].match(line):
            return line
        if HIERARCHY_PATTERNS["lettera"].match(line):
            return line
        if HIERARCHY_PATTERNS["punto"].match(line):
            return line
        if HIERARCHY_PATTERNS["numero"].match(line):
            return line
    return None


def add_overlap(chunks: list[str], index: int) -> str:
    chunk = chunks[index]
    if index == 0:
        return chunk
    prev_lines = chunks[index - 1].splitlines()
    overlap_size = max(3, int(len(prev_lines) * 0.25))
    overlap_lines = prev_lines[-overlap_size:]
    overlap_text = "\n".join(overlap_lines).strip()
    if overlap_text:
        return f"{overlap_text}\n{chunk}"
    return chunk


def prepend_context(section: ArticleSection, chunk: str, citation_key: str) -> str:
    hierarchy_text = " > ".join(section.hierarchy) if section.hierarchy else ""
    reform = ", ".join(extract_references(chunk)) or "nessuno"
    cross_refs = extract_cross_references(chunk)
    cross_text = ", ".join(f"{ref['ref_type']}: {ref['target']}" for ref in cross_refs) or "nessuno"
    effective_date = extract_effective_date(chunk) or "null"
    header = (
        f"Citazione normativa: {citation_key} - Titolo sezione: {section.section_title} - "
        f"Gerarchia: {hierarchy_text} - Riferimenti: {reform} - "
        f"Rinvii: {cross_text} - Data vigore: {effective_date}\n[Testo:] "
    )
    return f"{header}{chunk}".strip()


def split_long_chunk(chunk: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", chunk)
    parts = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if estimate_tokens(current + " " + sentence) <= 800:
            current = f"{current} {sentence}"
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def estimate_tokens_precise(text: str) -> int:
    base = len(text) / 4
    markdown_bonus = text.count("|") * 0.1
    list_bonus = sum(1 for line in text.splitlines() if line.strip().startswith(("-", "*", "1."))) * 0.5
    punctuation_bonus = sum(text.count(p) for p in [",", ";", ":"]) * 0.05
    return max(1, int(base + markdown_bonus + list_bonus + punctuation_bonus))


def extract_references(text: str) -> list[str]:
    refs = {
        f"{match.group(1)} {match.group(2)}/{match.group(3)}"
        for match in REF_PATTERN.finditer(text)
    }
    for match in REF_ART_PATTERN.finditer(text):
        refs.add(f"art. {match.group(1)} {match.group(2)} {match.group(3)}/{match.group(4)}")
    return sorted(refs)


def extract_cross_references(text: str) -> list[dict]:
    refs: list[dict] = []
    for ref_type, pattern in CROSS_REF_PATTERNS:
        for match in pattern.finditer(text):
            target = match.group(1).strip()
            refs.append({"ref_type": ref_type, "target": target})
    return refs


def extract_effective_date(text: str) -> Optional[str]:
    lowered = text.lower()
    if "entra in vigore" in lowered or "vigore dal" in lowered or "ha effetto dal" in lowered:
        dates = extract_dates(text)
        return dates[0] if dates else None
    return None


def extract_tags(text: str, nlp: Optional[object] = None) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)
    tags.extend(extract_entity_tags(text, nlp))
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)
    if len(unique_tags) < 5:
        unique_tags.append("normativa")
    return unique_tags[:10]


def extract_entity_tags(text: str, nlp: Optional[object]) -> list[str]:
    tags = []
    lowered = text.lower()
    if "gdpr" in lowered or "regolamento (ue) 2016/679" in lowered:
        tags.append("gdpr")
    if "sanzioni amministrative" in lowered:
        tags.append("sanzioni amministrative")
    if "datore di lavoro" in lowered:
        tags.append("obblighi datore di lavoro")
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_.lower() in {"org", "law", "event"}:
                tags.append(ent.text.lower())
    return tags


def summarize(text: str, citation_key: str, max_words: int, tags: list[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    keywords = set(tags)
    scored: list[tuple[float, str]] = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        score = 0.0
        lowered = sentence.lower()
        score += sum(1 for keyword in keywords if keyword in lowered)
        score += 0.2 * len(re.findall(r"\bdeve|devono|è vietato|obbligatorio\b", lowered))
        scored.append((score, sentence))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = []
    words_count = 0
    for _, sentence in scored:
        sentence_words = sentence.split()
        if words_count + len(sentence_words) <= max_words:
            selected.append(sentence)
            words_count += len(sentence_words)
        else:
            remaining = max_words - words_count
            if remaining > 0:
                selected.append(" ".join(sentence_words[:remaining]))
            break
    ent_text = ", ".join(tags[:3])
    prefix = f"Estratto da {citation_key}: "
    if ent_text:
        prefix += f"Principali obblighi/temi: {ent_text}. "
    return prefix + " ".join(selected)


def build_chunk_id(doc_slug: str, article_id: str, index: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", article_id.lower()).strip("_")
    return f"{doc_slug}_{slug}_{index}"


def build_citation_key(
    section: ArticleSection,
    context: dict,
    subsection: Optional[str],
) -> str:
    doc_title = context.get("doc_citation") or context.get("title", "Documento")
    base = f"{doc_title} {section.article_id}"
    if subsection:
        base += f" {normalize_subsection_label(subsection)}"
    return base.strip()


def normalize_subsection_label(label: str) -> str:
    lowered = label.lower()
    lowered = lowered.replace("comma", "comma")
    lowered = lowered.replace("co.", "comma").replace("c.", "comma")
    if re.match(r"^[a-z]\)", lowered):
        lowered = f"lettera {lowered}"
    lowered = lowered.replace("numero", "numero")
    return lowered.strip()


def document_slug(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", Path(filename).stem.lower()).strip("_")


def extract_doc_citation(title: str) -> Optional[str]:
    match = REF_PATTERN.search(title)
    if match:
        return f"{match.group(1)} {match.group(2)}/{match.group(3)}"
    lowered = title.lower()
    number_match = re.search(r"n\.\s*(\d{1,4})", lowered)
    date_match = DATE_PATTERNS[1].search(lowered) or DATE_PATTERNS[0].search(lowered)
    if number_match and date_match:
        year = date_match.groups()[-1]
        if "decreto legislativo" in lowered:
            return f"D.Lgs. {number_match.group(1)}/{year}"
        if "decreto legge" in lowered:
            return f"D.L. {number_match.group(1)}/{year}"
        if "legge" in lowered:
            return f"L. {number_match.group(1)}/{year}"
    return None


def validate_chunks(chunks: list[dict], original_text: str) -> list[dict]:
    unique = []
    seen = set()
    total_text = " ".join(chunk["full_chunk_text"] for chunk in chunks)
    coverage = len(set(original_text.split()))
    if coverage == 0:
        coverage_ratio = 0
    else:
        coverage_ratio = len(set(total_text.split())) / coverage
    if coverage_ratio < 0.95:
        logging.warning("Copertura testo originale %.1f%%", coverage_ratio * 100)

    for chunk in chunks:
        key = chunk["full_chunk_text"]
        if not key or key in seen:
            continue
        seen.add(key)
        if not chunk.get("citation_key"):
            logging.warning("Chunk senza citation_key: %s", chunk.get("chunk_id"))
        token_count = chunk["token_estimate"]
        if token_count < 50 or token_count > 1500:
            logging.warning("Chunk fuori range token (%s): %s", token_count, chunk.get("chunk_id"))
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
    tables: list[list[str]],
    warnings: list[str],
    nlp: Optional[object],
) -> dict:
    title = detect_title(text, Path(source_filename).stem)
    dates = extract_dates(text, nlp)
    metadata = {
        "source_filename": source_filename,
        "title": title,
        "publication_date": dates[0] if dates else None,
        "last_amendment_date": dates[-1] if dates else None,
        "norm_type": detect_norm_type(title),
        "total_pages": total_pages,
        "total_chunks": len(chunks),
        "processed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "norm_citations": sorted({ref for chunk in chunks for ref in chunk["reform_references"]}),
        "coordinated_text": bool(re.search(r"testo coordinato", text, re.IGNORECASE)),
        "warnings": warnings,
    }
    if tables:
        metadata["tables_detected"] = len(tables)
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
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    sub_el = ET.SubElement(child, sub_key)
                    sub_el.text = str(sub_value)
            else:
                child.text = "" if value is None else str(value)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def process_pdf(path: Path, output_folder: Path, output_format: str, use_ocr: bool) -> None:
    output_suffix = "json" if output_format == "json" else "xml"
    output_path = output_folder / f"{path.stem}_cleaned.{output_suffix}"
    if output_path.exists():
        logging.info("File già pulito: skipped (%s)", path.name)
        return

    try:
        raw_text, total_pages, tables = extract_text_pdf(path, use_ocr)
    except Exception as exc:
        logging.error("Errore estrazione %s: %s", path.name, exc)
        return

    nlp = load_spacy_model()
    cleaned_text = normalize_text(raw_text, nlp)
    sections, warnings = parse_hierarchy(cleaned_text, nlp)
    doc_slug = document_slug(path.name)

    title = detect_title(cleaned_text, path.stem)
    context = {"title": title, "doc_citation": extract_doc_citation(title), "nlp": nlp}
    chunks: list[dict] = []
    for section in sections:
        chunks.extend(split_into_chunks(section, doc_slug, context))

    if tables:
        table_section = ArticleSection(
            article_id="Tabelle",
            section_title="Tabelle estratte",
            hierarchy=["Allegati"],
            text="\n".join("\n".join(lines) for lines in tables),
            is_annex=True,
        )
        chunks.extend(split_into_chunks(table_section, doc_slug, context))

    chunks = validate_chunks(chunks, cleaned_text)
    log_stats(chunks)
    output = build_output(path.name, cleaned_text, total_pages, chunks, tables, warnings, nlp)

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
    use_ocr: bool = False,
) -> None:
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    if not input_path.exists():
        raise FileNotFoundError(f"Cartella input non trovata: {input_folder}")

    for pdf_path in iter_pdf_files(input_path, recursive):
        process_pdf(pdf_path, output_path, output_format, use_ocr)


def build_rag_fields(
    citation_key: str,
    tags: list[str],
    summary_50: str,
    summary_150: str,
    context: dict,
    reform_refs: list[str],
    cross_refs: list[dict],
    effective_date: Optional[str],
) -> dict:
    hybrid_keywords = list({*tags, *summary_50.split()[:10], *summary_150.split()[:20]})
    return {
        "hybrid_keywords": hybrid_keywords,
        "filterable_metadata": {
            "citation_key": citation_key,
            "tags": tags,
            "title": context.get("title"),
            "effective_date": effective_date,
            "reform_references": reform_refs,
            "cross_references": cross_refs,
        },
    }


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Processa PDF normativi per RAG.")
    parser.add_argument("--input_folder", required=True, help="Cartella contenente PDF")
    parser.add_argument("--output_folder", required=True, help="Cartella output")
    parser.add_argument("--format", choices=["json", "xml"], default="json")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--ocr", action="store_true", help="Usa OCR se possibile")
    parser.add_argument("--quiet", action="store_true", help="Riduci logging")
    return parser


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        process_folder(
            input_folder=args.input_folder,
            output_folder=args.output_folder,
            output_format=args.format,
            recursive=args.recursive,
            use_ocr=args.ocr,
        )
    except Exception as exc:
        logging.error("Errore: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
