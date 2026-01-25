from __future__ import annotations

import re
from typing import Iterable

from normativa_processor.core.models import NormReference

REF_PATTERN = re.compile(
    r"\b(Legge|L\.|D\.?Lgs\.|D\.?L\.|DPR|Regolamento|Direttiva)\s*"
    r"(\d{1,4})/(\d{4})",
    re.IGNORECASE,
)

ENHANCED_REF_PATTERNS = {
    "legge": re.compile(
        r"\b(?:L(?:egge)?\.?)\s*(?:n\.\s*)?(\d{1,4})(?:\s*/\s*|\s+del\s+)(\d{4})",
        re.IGNORECASE,
    ),
    "decreto_legislativo": re.compile(
        r"\b(?:D\.?\s*Lgs\.?|Decreto\s+Legislativo)\s*(?:n\.\s*)?(\d{1,4})"
        r"(?:\s*/\s*|\s+del\s+)(\d{4})",
        re.IGNORECASE,
    ),
    "decreto_legge": re.compile(
        r"\b(?:D\.?\s*L\.?|Decreto\s+Legge)\s*(?:n\.\s*)?(\d{1,4})(?:\s*/\s*|\s+del\s+)(\d{4})",
        re.IGNORECASE,
    ),
    "dpr": re.compile(
        r"\b(?:D\.?P\.?R\.?|Decreto\s+del\s+Presidente\s+della\s+Repubblica)\s*"
        r"(?:n\.\s*)?(\d{1,4})(?:\s*/\s*|\s+del\s+)(\d{4})",
        re.IGNORECASE,
    ),
    "direttiva_ue": re.compile(
        r"\b(?:Direttiva|Dir\.)\s*(?:\(UE\)|\(CE\))?\s*(?:n\.\s*)?(\d{4})/(\d{1,4})",
        re.IGNORECASE,
    ),
    "regolamento_ue": re.compile(
        r"\b(?:Regolamento|Reg\.)\s*(?:\(UE\)|\(CE\))?\s*(?:n\.\s*)?(\d{4})/(\d{1,4})",
        re.IGNORECASE,
    ),
}

ENHANCED_ART_PATTERN = re.compile(
    r"\bart(?:icolo|\.)?\s*(\d+(?:[- ][a-z]+)?)"
    r"(?:\s*,?\s*comma\s*(\d+(?:[- ][a-z]+)?))?"
    r"(?:\s*,?\s*lettera\s*([a-z]+\)?))?"
    r"(?:\s*,?\s*numero\s*(\d+))?"
    r"\s+(?:del(?:la)?|dell')\s*"
    r"(Legge|L\.|D\.?Lgs\.?|D\.?L\.?|DPR|Regolamento|Direttiva)\s*(?:n\.\s*)?"
    r"(\d{1,4})\s*/\s*(\d{4})",
    re.IGNORECASE,
)


def _normalize_norm_type(raw: str) -> str:
    mapping = {
        "l.": "legge",
        "legge": "legge",
        "d.lgs.": "decreto_legislativo",
        "d.lgs": "decreto_legislativo",
        "d.l.": "decreto_legge",
        "d.l": "decreto_legge",
        "dpr": "dpr",
        "regolamento": "regolamento",
        "direttiva": "direttiva",
    }
    return mapping.get(raw.lower().strip(), "altro")


def extract_references_enhanced(text: str) -> list[NormReference]:
    references: list[NormReference] = []
    seen = set()

    for norm_type, pattern in ENHANCED_REF_PATTERNS.items():
        for match in pattern.finditer(text):
            if norm_type in {"direttiva_ue", "regolamento_ue"}:
                year, number = match.groups()
            else:
                number, year = match.groups()
            ref = NormReference(norm_type=norm_type, number=number, year=year, full_text=match.group(0))
            citation = ref.to_citation()
            if citation not in seen:
                references.append(ref)
                seen.add(citation)

    for match in ENHANCED_ART_PATTERN.finditer(text):
        article, comma, letter, point, norm_type, number, year = match.groups()
        ref = NormReference(
            norm_type=_normalize_norm_type(norm_type),
            number=number,
            year=year,
            article=article,
            comma=comma,
            letter=letter.rstrip(")") if letter else None,
            point=point,
            full_text=match.group(0),
        )
        citation = ref.to_citation()
        if citation not in seen:
            references.append(ref)
            seen.add(citation)

    return references


def extract_references(text: str) -> list[str]:
    refs = {f"{match.group(1)} {match.group(2)}/{match.group(3)}" for match in REF_PATTERN.finditer(text)}
    enhanced = extract_references_enhanced(text)
    for ref in enhanced:
        refs.add(ref.to_citation())
    return sorted(refs)


def extract_cross_references(text: str) -> list[dict]:
    patterns: Iterable[tuple[str, re.Pattern[str]]] = [
        ("modifica", re.compile(r"come modificato da\s+([^\.;\n]+)", re.IGNORECASE)),
        ("sostituzione", re.compile(r"sostituito da\s+([^\.;\n]+)", re.IGNORECASE)),
        ("abrogazione", re.compile(r"abrogato da\s+([^\.;\n]+)", re.IGNORECASE)),
        ("abrogazione", re.compile(r"abrogato dall'?art\.\s*([^\.;\n]+)", re.IGNORECASE)),
        ("rinvio", re.compile(r"ai sensi dell'art\.\s*([^\.;\n]+)", re.IGNORECASE)),
        ("rinvio", re.compile(r"ai sensi dell'articolo\s*([^\.;\n]+)", re.IGNORECASE)),
        ("modifica", re.compile(r"\[(?:modificato|sostituito)\s+da\s+([^\]]+)\]", re.IGNORECASE)),
    ]
    refs: list[dict] = []
    for ref_type, pattern in patterns:
        for match in pattern.finditer(text):
            refs.append({"ref_type": ref_type, "target": match.group(1).strip()})
    return refs
