"""Alembic environment. Models are imported so autogenerate/`compare_metadata` can see them."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, pool

import app.db.models  # noqa: F401  (registers tables on Base.metadata)
from alembic import context
from app.db.models.base import Base

config = context.config
target_metadata = Base.metadata


def _dotenv() -> dict[str, str]:
    """Minimal .env reader (repo root) so `alembic upgrade head` works without exporting variables."""
    path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def database_url() -> str:
    env = {**_dotenv(), **os.environ}
    if url := env.get("DATABASE_URL"):
        return url
    return "postgresql+psycopg://{u}:{p}@{h}:{port}/{db}".format(
        u=env["POSTGRES_USER"], p=env["POSTGRES_PASSWORD"], h=env.get("POSTGRES_HOST", "localhost"),
        port=env.get("POSTGRES_PORT", "5432"), db=env["POSTGRES_DB"],
    )


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A caller (tests) may hand in an open connection through config.attributes.
    connection = config.attributes.get("connection")
    if connection is None:
        engine = create_engine(database_url(), poolclass=pool.NullPool)
        with engine.connect() as connection:
            _run(connection)
    else:
        _run(connection)


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
