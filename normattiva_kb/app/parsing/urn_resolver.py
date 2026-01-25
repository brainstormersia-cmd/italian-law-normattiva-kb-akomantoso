from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.parsing.references import ALIASES, ART_PATTERN


def _build_urn(base_urn: str, article: str | None, comma: str | None, letter: str | None, number: str | None) -> str:
    parts = [base_urn]
    if article:
        parts.append(f"art:{article}")
    if comma:
        parts.append(f"c:{comma}")
    if letter:
        parts.append(f"lett:{letter}")
    if number:
        parts.append(f"num:{number}")
    if len(parts) == 1:
        return base_urn
    return "#".join([parts[0], "/".join(parts[1:])])


def _match_alias(text: str) -> Optional[str]:
    lowered = text.lower()
    for alias, canonical in ALIASES.items():
        if alias.lower() in lowered:
            return canonical
    return None


class UrnResolver:
    def __init__(self, document_urn: Optional[str]) -> None:
        self.document_urn = document_urn

    @lru_cache(maxsize=1024)
    def resolve(self, match_text: str, context_text: str = "") -> tuple[Optional[str], float, str]:
        combined = " ".join(part for part in (match_text, context_text) if part).strip()
        if not combined:
            return None, 0.0, "manual"

        if match_text.startswith("urn:"):
            return match_text, 0.95, "explicit"
        if "urn:" in combined:
            return combined[combined.index("urn:") :].split()[0], 0.9, "explicit"

        match = ART_PATTERN.search(match_text) or ART_PATTERN.search(combined)
        if match and self.document_urn:
            article, comma, letter, number = match.groups()
            return _build_urn(self.document_urn, article, comma, letter, number), 0.7, "contextual"

        alias_doc = _match_alias(combined)
        if alias_doc:
            if match:
                article, comma, letter, number = match.groups()
                return _build_urn(alias_doc, article, comma, letter, number), 0.6, "heuristic"
            return alias_doc, 0.55, "heuristic"

        if match:
            return None, 0.35, "manual"

        return None, 0.1, "manual"
