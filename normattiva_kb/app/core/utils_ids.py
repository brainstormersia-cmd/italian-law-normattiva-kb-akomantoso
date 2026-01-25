from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_doc_id(doc_type: str, number: str | None, year: str | None) -> str:
    number_part = number or "0"
    year_part = year or "0"
    return f"{doc_type}:{number_part}:{year_part}"


def canonical_node_id(doc_id: str, version_id: str, path: str) -> str:
    return sha256_text(f"{doc_id}:{version_id}:{path}")
