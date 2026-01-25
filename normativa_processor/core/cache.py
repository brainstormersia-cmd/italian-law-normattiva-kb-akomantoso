from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any


class PDFProcessorCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_key(self, pdf_path: Path) -> str:
        stat = pdf_path.stat()
        content = f"{pdf_path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, pdf_path: Path) -> dict | None:
        cache_key = self.get_cache_key(pdf_path)
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if not cache_file.exists():
            return None
        try:
            with cache_file.open("rb") as handle:
                return pickle.load(handle)
        except Exception as exc:
            logging.warning("Cache corrotta per %s: %s", pdf_path.name, exc)
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, pdf_path: Path, result: dict) -> None:
        cache_key = self.get_cache_key(pdf_path)
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        with cache_file.open("wb") as handle:
            pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
