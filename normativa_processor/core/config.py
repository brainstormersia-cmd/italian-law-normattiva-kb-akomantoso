from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
import importlib.util
import importlib


def _load_yaml() -> Any:
    if importlib.util.find_spec("yaml"):
        return importlib.import_module("yaml")
    return None


@dataclass
class ProcessingConfig:
    target_chunk_tokens: int = 800
    max_chunk_tokens: int = 1500
    min_chunk_tokens: int = 50
    _VALID_TOKEN_RANGE: ClassVar[tuple[int, int]] = (10, 5000)

    def __post_init__(self) -> None:
        if not (self._VALID_TOKEN_RANGE[0] <= self.min_chunk_tokens <= self._VALID_TOKEN_RANGE[1]):
            raise ValueError(f"min_chunk_tokens deve essere tra {self._VALID_TOKEN_RANGE}")
        if not (self.min_chunk_tokens < self.target_chunk_tokens < self.max_chunk_tokens):
            raise ValueError("Deve valere: min < target < max tokens")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProcessingConfig":
        defaults = cls()
        values = {field: data.get(field, getattr(defaults, field)) for field in cls.__dataclass_fields__}
        return cls(**values)


class Config:
    _config: dict[str, Any] = {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> None:
        if path is None:
            cls._config = cls._defaults()
            return

        path_obj = Path(path)
        if not path_obj.exists():
            logging.warning("Config file non trovato: %s, uso defaults", path_obj)
            cls._config = cls._defaults()
            return

        if path_obj.suffix.lower() in {".yaml", ".yml"}:
            yaml = _load_yaml()
            if yaml is None:
                logging.warning("PyYAML non disponibile, uso defaults")
                cls._config = cls._defaults()
                return
            with path_obj.open("r", encoding="utf-8") as handle:
                cls._config = yaml.safe_load(handle) or {}
                return

        try:
            cls._config = json.loads(path_obj.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Config JSON invalido: {exc}") from exc

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        if not cls._config:
            cls._config = cls._defaults()
        value: Any = cls._config
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default
        return default if value is None else value

    @classmethod
    def _defaults(cls) -> dict[str, Any]:
        return {
            "processing": {
                "target_chunk_tokens": 800,
                "max_chunk_tokens": 1500,
                "min_chunk_tokens": 50,
            },
            "summarization": {"strategy": "keyword"},
            "cache": {"enabled": False, "directory": ".cache/normativa"},
            "parallel": {"enabled": False, "max_workers": 4},
        }

    @classmethod
    def processing_config(cls) -> ProcessingConfig:
        data = cls.get("processing", {})
        return ProcessingConfig.from_mapping(data)
