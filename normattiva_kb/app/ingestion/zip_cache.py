from __future__ import annotations

import zipfile
from pathlib import Path


def extract_zip_to_cache(zip_path: Path, cache_dir: Path) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.namelist():
            if member.lower().endswith(".xml"):
                target = cache_dir / Path(member).name
                with zip_ref.open(member) as source, target.open("wb") as dest:
                    dest.write(source.read())
                extracted.append(target)
    return extracted
