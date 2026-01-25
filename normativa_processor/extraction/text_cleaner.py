from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

LIGATURES = {
    "ﬁ": "fi",
    "ﬀ": "ff",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
}

BOILERPLATE_PATTERNS = [
    re.compile(r"Gazzetta Ufficiale\s+n\.\s*\d+\s+del\s+\d{1,2}\s+\w+\s+\d{4}", re.IGNORECASE),
    re.compile(r"Serie Generale", re.IGNORECASE),
    re.compile(r"^Visto il\b", re.IGNORECASE),
    re.compile(r"^Visti\b", re.IGNORECASE),
    re.compile(r"^Considerato che\b", re.IGNORECASE),
    re.compile(r"^Ritenuto\b", re.IGNORECASE),
]


def remove_repeated_headers(
    pages_text: Iterable[str], headers: list[str], footers: list[str]
) -> str:
    header_counts = Counter(headers)
    footer_counts = Counter(footers)
    total_pages = len(headers)
    repeated_headers = {
        h for h, count in header_counts.items() if count >= max(2, int(total_pages * 0.6))
    }
    repeated_footers = {
        f for f, count in footer_counts.items() if count >= max(2, int(total_pages * 0.6))
    }
    cleaned_pages = []
    for text in pages_text:
        lines = [line.strip() for line in text.splitlines()]
        filtered = []
        for line in lines:
            if not line:
                filtered.append("")
                continue
            if line in repeated_headers or line in repeated_footers:
                continue
            if re.fullmatch(r"\d{1,4}", line):
                continue
            if re.search(r"\bBOZZA\b|\bG\.U\.\b", line):
                continue
            filtered.append(line)
        cleaned_pages.append("\n".join(filtered))
    return "\n".join(cleaned_pages)


def normalize_legal_abbreviations(text: str) -> str:
    replacements = {
        "d.lgs.": "D.Lgs.",
        "d.l.": "D.L.",
        "d.p.r.": "DPR",
        "l.": "L.",
    }
    for src, tgt in replacements.items():
        text = re.sub(re.escape(src), tgt, text, flags=re.IGNORECASE)
    return text


def remove_boilerplate(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in BOILERPLATE_PATTERNS):
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_text(text: str) -> str:
    for src, tgt in LIGATURES.items():
        text = text.replace(src, tgt)
    text = normalize_legal_abbreviations(text)
    text = remove_boilerplate(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()
