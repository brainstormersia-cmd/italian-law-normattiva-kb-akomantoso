from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import get_settings


def get_async_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, future=True)


AsyncSessionLocal = async_sessionmaker(bind=get_async_engine(), expire_on_commit=False)
