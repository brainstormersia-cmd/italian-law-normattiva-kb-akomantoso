from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
