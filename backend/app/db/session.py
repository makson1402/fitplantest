"""Async engine construction. Alembic uses the sync psycopg driver; the application uses asyncpg."""
from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def async_database_url(url: str) -> str:
    """Accept any `postgresql[+driver]://` URL (e.g. the one Alembic uses) and return the asyncpg form."""
    return make_url(url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


def create_engine_from_url(url: str, *, pool_size: int = 10) -> AsyncEngine:
    return create_async_engine(async_database_url(url), pool_size=pool_size, pool_pre_ping=True)
