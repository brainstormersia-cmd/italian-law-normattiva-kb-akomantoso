from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Optional

from normativa_processor.core.types import NLPModelType

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


def normalize_dates(text: str, nlp: NLPModelType) -> str:
    def replace_match(match: re.Match[str]) -> str:
        day, month, year = match.groups()
        month_number = month_name_to_number(month) if month.isalpha() else month
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


def extract_dates(text: str, nlp: NLPModelType = None) -> list[str]:
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


def extract_doc_citation(title: str) -> Optional[str]:
    from normativa_processor.parsing.reference_parser import REF_PATTERN

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


def build_metadata(
    source_filename: str,
    text: str,
    total_pages: int,
    total_chunks: int,
    nlp: NLPModelType,
    warnings: list[str],
) -> dict:
    title = detect_title(text, Path(source_filename).stem)
    dates = extract_dates(text, nlp)
    return {
        "source_filename": source_filename,
        "title": title,
        "publication_date": dates[0] if dates else None,
        "last_amendment_date": dates[-1] if dates else None,
        "norm_type": detect_norm_type(title),
        "total_pages": total_pages,
        "total_chunks": total_chunks,
        "processed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "coordinated_text": bool(re.search(r"testo coordinato", text, re.IGNORECASE)),
        "warnings": warnings,
    }
