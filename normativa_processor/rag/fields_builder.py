from __future__ import annotations

from typing import Optional


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
