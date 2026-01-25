from __future__ import annotations

import logging

from normativa_processor.core.config import ProcessingConfig


def validate_chunks(chunks: list[dict], original_text: str, config: ProcessingConfig) -> list[dict]:
    unique = []
    seen = set()
    total_text = " ".join(chunk["full_chunk_text"] for chunk in chunks)
    coverage = len(set(original_text.split()))
    if coverage == 0:
        coverage_ratio = 0
    else:
        coverage_ratio = len(set(total_text.split())) / coverage
    if coverage_ratio < 0.95:
        logging.warning("Copertura testo originale %.1f%%", coverage_ratio * 100)

    for chunk in chunks:
        key = chunk["full_chunk_text"]
        if not key or key in seen:
            continue
        seen.add(key)
        if not chunk.get("citation_key"):
            logging.warning("Chunk senza citation_key: %s", chunk.get("chunk_id"))
        token_count = chunk["token_estimate"]
        if token_count < config.min_chunk_tokens or token_count > config.max_chunk_tokens:
            logging.warning("Chunk fuori range token (%s): %s", token_count, chunk.get("chunk_id"))
        unique.append(chunk)
    return unique
