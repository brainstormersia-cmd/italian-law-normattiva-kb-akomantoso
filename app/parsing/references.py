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
    "CITES": re.compile(r"ai sensi di|a norma di|ex art", re.IGNORECASE),
}


def extract_references(text: str) -> list[dict]:
    """
    ✅ VERSIONE CORRETTA: Garantisce che ogni riferimento abbia sempre raw_snippet
    """
    refs: list[dict] = []
    lowered = text.lower()
    
    # Estrazione alias
    for alias, canonical in ALIASES.items():
        if alias.lower() in lowered:
            position = lowered.index(alias.lower())
            refs.append(
                {
                    "match_text": alias,
                    "raw_snippet": _snippet(text, position),  # ✅ Sempre presente
                    "target_canonical_doc": canonical,
                    "relation_type": "CITES",
                    "confidence": 0.6,
                    "method": "alias:v1",
                }
            )

    # Estrazione atti normativi
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
                    "raw_snippet": _snippet(text, match.start()),  # ✅ Sempre presente
                    "target_canonical_doc": canonical,
                    "relation_type": relation_type,
                    "confidence": confidence,
                    "method": "regex:v1",
                }
            )

    # Estrazione articoli
    for match in ART_PATTERN.finditer(text):
        article, comma, letter, number = match.groups()
        snippet = _snippet(text, match.start())
        
        refs.append(
            {
                "match_text": match.group(0),
                "raw_snippet": snippet,  # ✅ Sempre presente
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
    """Rileva il tipo di relazione tra norme."""
    for relation, pattern in RELATION_PATTERNS.items():
        if pattern.search(text):
            return relation
    return "CITES"


def _snippet(text: str, position: int, width: int = 200) -> str:
    """
    ✅ VERSIONE CORRETTA: Ritorna sempre una stringa non-vuota
    """
    if not text:
        return "(testo vuoto)"
    
    start = max(0, position - width)
    end = min(len(text), position + width)
    snippet = text[start:end].strip()
    
    # ✅ Garantisce che lo snippet non sia mai vuoto
    return snippet if snippet else text[:min(400, len(text))]