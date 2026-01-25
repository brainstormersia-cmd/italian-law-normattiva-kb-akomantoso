from __future__ import annotations

import hashlib
from pathlib import Path
import datetime as dt


def compute_sha256(path: Path) -> str:
    hash_obj = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def raw_file_record(path: Path, derived_from: int | None = None, is_from_zip: bool = False) -> dict:
    stat = path.stat()
    return {
        "original_path": str(path),
        "derived_from_raw_id": derived_from,
        "is_from_zip": is_from_zip,
        "sha256": compute_sha256(path),
        "size": stat.st_size,
        "mtime": dt.datetime.fromtimestamp(stat.st_mtime),
        "status": "new",
        "error": None,
    }
