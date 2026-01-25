from __future__ import annotations

from pathlib import Path


def scan_inputs(input_dir: str) -> list[Path]:
    path = Path(input_dir)
    return sorted(list(path.glob("**/*.xml")) + list(path.glob("**/*.zip")))
