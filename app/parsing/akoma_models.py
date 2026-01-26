from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ReferenceOut(BaseModel):
    href: str
    text: str


class NodeOut(BaseModel):
    eId: Optional[str] = Field(default=None)
    canonical_path: str
    text_content: str
    text_xml_fragment: Optional[str] = None
    level: int
    references: list[ReferenceOut] = Field(default_factory=list)


class DocumentOut(BaseModel):
    urn: Optional[str]
    work_urn: Optional[str]
    expression_urn: Optional[str]
    manifestation_urn: Optional[str]
    publication_date: Optional[str]
    version_date: Optional[str]
    nodes: list[NodeOut]
