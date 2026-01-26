from __future__ import annotations

from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os


def load_env() -> None:
    load_dotenv()


class Settings(BaseModel):
    database_url: str = Field(..., alias="DATABASE_URL")
    input_dir: str = Field("/data", alias="INPUT_DIR")
    cache_dir: str = Field(".cache/normattiva", alias="CACHE_DIR")
    log_level: str = Field("INFO", alias="LOG_LEVEL")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        load_env()
        _settings = Settings(**os.environ)
    return _settings
