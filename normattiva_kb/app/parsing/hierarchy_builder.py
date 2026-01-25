from __future__ import annotations

from app.core.utils_ids import canonical_doc_id


def build_sort_key(path: str) -> str:
    return path.replace("/", "_")


def canonical_path(parts: list[str]) -> str:
    return "/".join(parts)
