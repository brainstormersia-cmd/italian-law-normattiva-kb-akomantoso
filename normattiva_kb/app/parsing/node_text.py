from __future__ import annotations

from app.core.utils_text import normalize_whitespace


def extract_text(element) -> str:
    if element is None:
        return ""
    text = " ".join(element.itertext())
    return text


def clean_text(text: str) -> str:
    return normalize_whitespace(text)
