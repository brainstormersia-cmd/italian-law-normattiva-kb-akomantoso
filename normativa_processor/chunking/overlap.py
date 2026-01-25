from __future__ import annotations


def add_overlap(chunks: list[str], index: int, overlap_ratio: float) -> str:
    chunk = chunks[index]
    if index == 0:
        return chunk
    prev_lines = chunks[index - 1].splitlines()
    overlap_size = max(3, int(len(prev_lines) * overlap_ratio))
    overlap_lines = prev_lines[-overlap_size:]
    overlap_text = "\n".join(overlap_lines).strip()
    if overlap_text:
        return f"{overlap_text}\n{chunk}"
    return chunk
