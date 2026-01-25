from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    doc_id: str
    canonical_doc: str
    doc_type: str
    number: int | None
    year: int | None
    title: str | None


class NodeOut(BaseModel):
    node_id: str
    canonical_path: str
    node_type: str
    label: str
    text_clean: str
