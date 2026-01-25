from __future__ import annotations

import re


def estimate_tokens_precise(text: str) -> int:
    words = len(re.findall(r"\b\w+\b", text))
    punctuation = sum(text.count(p) for p in ".,;:!?()[]{}")
    markdown_tokens = text.count("|") + text.count("#")
    list_items = len([line for line in text.splitlines() if line.strip().startswith(("-", "*", "+"))])
    return max(1, int(words * 1.3 + punctuation * 0.1 + markdown_tokens * 0.5 + list_items * 2))
