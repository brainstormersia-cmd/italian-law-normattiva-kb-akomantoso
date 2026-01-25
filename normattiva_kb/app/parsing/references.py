from __future__ import annotations

import re
from app.core.utils_ids import canonical_doc_id

ALIASES = {
    "TUIR": "dpr:917:1986",
    "Statuto del contribuente": "l:212:2000",
}

ACT_PATTERNS = [
    ("dlgs", re.compile(r"decreto legislativo n\.\s*(\d+)\s+del\s+(\d{4})", re.IGNORECASE)),
    ("dlgs", re.compile(r"d\.lgs\.\s*(\d+)/(\d{4})", re.IGNORECASE)),
    ("dpr", re.compile(r"d\\.?p\\.?r\\.?\\s*(\\d+)/(\\d{4})", re.IGNORECASE)),
    ("l", re.compile(r"legge\s*(\d+)/(\d{4})", re.IGNORECASE)),
    ("l", re.compile(r"l\.\s*n\.\s*(\d+)/(\d{4})", re.IGNORECASE)),
]

ART_PATTERN = re.compile(
    r"art(?:icolo|\.)\s*(\d+[a-z-]*)"
    r"(?:,\s*comma\s*(\d+[a-z-]*))?"
    r"(?:,\s*lettera\s*([a-z]))?"
    r"(?:,\s*n\.\s*(\d+))?",
    re.IGNORECASE,
)

RELATION_PATTERNS = {
    "AMENDS": re.compile(r"modificato da|sostituito da|inserito da", re.IGNORECASE),
    "REPEALS": re.compile(r"abrogato", re.IGNORECASE),
    "DEROGATES": re.compile(r"in deroga a", re.IGNORECASE),
}


def extract_references(text: str) -> list[dict]:
    refs: list[dict] = []
    lowered = text.lower()
    for alias, canonical in ALIASES.items():
        if alias.lower() in lowered:
            refs.append(
                {
                    "match_text": alias,
                    "raw_snippet": _snippet(text, lowered.index(alias.lower())),
                    "target_canonical_doc": canonical,
                    "relation_type": "CITES",
                    "confidence": 0.6,
                    "method": "alias:v1",
                }
            )

    for doc_type, pattern in ACT_PATTERNS:
        for match in pattern.finditer(text):
            number, year = match.groups()
            canonical = canonical_doc_id(doc_type, number, year)
            relation_type = _detect_relation(text)
            confidence = 0.6
            if ART_PATTERN.search(text[max(0, match.start() - 80) : match.end() + 80]):
                confidence = 0.9
            refs.append(
                {
                    "match_text": match.group(0),
                    "raw_snippet": _snippet(text, match.start()),
                    "target_canonical_doc": canonical,
                    "relation_type": relation_type,
                    "confidence": confidence,
                    "method": "regex:v1",
                }
            )

    for match in ART_PATTERN.finditer(text):
        article, comma, letter, number = match.groups()
        refs.append(
            {
                "match_text": match.group(0),
                "raw_snippet": _snippet(text, match.start()),
                "target_article": article,
                "target_comma": comma,
                "target_letter": letter,
                "target_number": number,
                "relation_type": _detect_relation(text),
                "confidence": 0.4,
                "method": "regex:v1",
            }
        )

    return refs


def _detect_relation(text: str) -> str:
    for relation, pattern in RELATION_PATTERNS.items():
        if pattern.search(text):
            return relation
    return "CITES"


def _snippet(text: str, position: int, width: int = 200) -> str:
    start = max(0, position - width)
    end = min(len(text), position + width)
    return text[start:end]
