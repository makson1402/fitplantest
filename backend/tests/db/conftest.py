"""Fixtures for tests that need a real PostgreSQL (`docker compose up -d postgres`).

They run against a throwaway database created next to the dev one, so the dev data is never touched.
Skipped automatically when PostgreSQL is not reachable.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

from alembic import command

BACKEND = Path(__file__).resolve().parents[2]


def _admin_url() -> URL:
    env = dict(os.environ)
    dotenv = BACKEND.parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env.setdefault(key.strip(), value.strip())
    if env.get("DATABASE_URL"):
        return make_url(env["DATABASE_URL"])
    return URL.create(
        "postgresql+psycopg",
        username=env.get("POSTGRES_USER"),
        password=env.get("POSTGRES_PASSWORD"),
        host=env.get("POSTGRES_HOST", "localhost"),
        port=int(env.get("POSTGRES_PORT", "5432")),
        database=env.get("POSTGRES_DB"),
    )


def _throwaway_database(seed: bool):
    """Create a migrated (optionally seeded) database next to the dev one; drop it afterwards."""
    admin = _admin_url()
    admin_engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL is not reachable: {exc.__class__.__name__}")
    name = f"fitplan_test_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(admin.set(database=name))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    if seed:
        loader = BACKEND.parent / "database" / "seed" / "load.py"
        if not loader.exists():
            pytest.skip("database/ is not part of this checkout")
        spec = importlib.util.spec_from_file_location("seed_load", loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import psycopg

        with psycopg.connect(admin.set(database=name, drivername="postgresql").render_as_string(hide_password=False)) as c:
            module.load(c)
            c.commit()
    yield engine
    engine.dispose()
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def pg_engine() -> Engine:
    """Empty migrated database. Tests here insert rows of their own (e.g. user deletion)."""
    yield from _throwaway_database(seed=False)


@pytest.fixture(scope="session")
def seeded_engine() -> Engine:
    """Migrated database with the reference seeds loaded; tests must treat the reference data as read-only."""
    yield from _throwaway_database(seed=True)
