from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ArticleSection:
    article_id: str
    section_title: str
    hierarchy: list[str]
    text: str
    is_annex: bool = False


@dataclass
class NormReference:
    norm_type: str
    number: str
    year: str
    article: Optional[str] = None
    comma: Optional[str] = None
    letter: Optional[str] = None
    point: Optional[str] = None
    full_text: str = ""

    def to_citation(self) -> str:
        base = f"{self.norm_type} {self.number}/{self.year}"
        if self.article:
            base += f", art. {self.article}"
        if self.comma:
            base += f", comma {self.comma}"
        if self.letter:
            base += f", lett. {self.letter}"
        if self.point:
            base += f", n. {self.point}"
        return base
