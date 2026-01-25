from __future__ import annotations

from typing import Optional


def build_rag_fields(
    citation_key: str,
    context: dict,
    hierarchy: list[str],
    effective_date: Optional[str],
) -> dict:
    return {
        "hybrid_keywords": [],
        "filterable_metadata": {
            "citation_key": citation_key,
            "title": context.get("title"),
            "effective_date": effective_date,
            "hierarchy": hierarchy,
        },
    }
