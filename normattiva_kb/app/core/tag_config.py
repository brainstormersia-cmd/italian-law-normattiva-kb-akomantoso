from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TagConfig:
    structural_tags: frozenset[str]
    container_tags: frozenset[str]
    inline_tags: frozenset[str]
    metadata_tags: frozenset[str]


DEFAULT_TAG_CONFIG = TagConfig(
    structural_tags=frozenset({
        "act",
        "chapter",
        "section",
        "article",
        "book",
        "title",
        "part",
    }),
    container_tags=frozenset({
        "paragraph",
        "point",
        "letter",
        "subparagraph",
        "list",
        "item",
    }),
    inline_tags=frozenset({
        "ref",
        "ins",
        "del",
        "b",
        "i",
        "u",
        "sup",
        "sub",
        "span",
    }),
    metadata_tags=frozenset({
        "meta",
        "analysis",
        "notes",
        "ndr",
        "note",
    }),
)
