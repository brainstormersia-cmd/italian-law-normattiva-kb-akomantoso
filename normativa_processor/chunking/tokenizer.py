from __future__ import annotations

import importlib
import importlib.util
import logging
import re
from functools import lru_cache

from normativa_processor.chunking.tokenizer_fallback import estimate_tokens_precise


def _load_tiktoken():
    if importlib.util.find_spec("tiktoken"):
        return importlib.import_module("tiktoken")
    return None


@lru_cache(maxsize=1)
def get_tokenizer(model: str = "cl100k_base"):
    tiktoken = _load_tiktoken()
    if tiktoken is None:
        logging.warning("tiktoken non disponibile, uso stima approssimativa")
        return None
    try:
        return tiktoken.get_encoding(model)
    except Exception as exc:
        logging.warning("Errore tokenizer: %s", exc)
        return None


def estimate_tokens_accurate(text: str) -> int:
    tokenizer = get_tokenizer()
    if tokenizer:
        try:
            return len(tokenizer.encode(text))
        except Exception as exc:
            logging.debug("Errore tokenization: %s", exc)
    return estimate_tokens_precise(text)
