from __future__ import annotations

from app.core.utils_ids import canonical_doc_id


def canonical_node(doc_canonical: str, article: str | None, comma: str | None, letter: str | None, number: str | None) -> str:
    parts = [doc_canonical]
    if article:
        parts.append(f"art:{article}")
    if comma:
        parts.append(f"c:{comma}")
    if letter:
        parts.append(f"lett:{letter}")
    if number:
        parts.append(f"num:{number}")
    return "#".join([parts[0], "/".join(parts[1:])]) if len(parts) > 1 else parts[0]
