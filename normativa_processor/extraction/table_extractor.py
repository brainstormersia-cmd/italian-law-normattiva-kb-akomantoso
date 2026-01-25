from __future__ import annotations

from typing import Optional


def table_to_markdown(table: list[list[Optional[str]]]) -> list[str]:
    if not table:
        return []
    clean_rows = []
    for row in table:
        if not row:
            continue
        cleaned = []
        for cell in row:
            if not cell:
                cleaned.append("")
                continue
            cleaned.append(cell.replace("\n", "<br>").strip())
        clean_rows.append(cleaned)
    if not clean_rows:
        return []
    header = clean_rows[0]
    separator = ["---" for _ in header]
    md_lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(separator) + " |"]
    for row in clean_rows[1:]:
        md_lines.append("| " + " | ".join(row) + " |")
    return md_lines
