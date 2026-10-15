from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

import app.db.models  # noqa: F401
from app.db.models.base import Base

REPO = Path(__file__).resolve().parents[3]


def test_alembic_copy_equals_reviewed_sql():
    docs = REPO / "docs" / "database" / "schema_postgres.sql"
    copy = REPO / "backend" / "alembic" / "sql" / "0001_initial_schema.sql"
    if not docs.exists():
        pytest.skip("docs/ is not part of this checkout")
    assert docs.read_text(encoding="utf-8") == copy.read_text(encoding="utf-8"), (
        "docs/database/schema_postgres.sql changed: add a new Alembic migration, do not edit 0001"
    )


def test_models_match_migrated_database(pg_engine):
    """Autogenerate must find nothing to change: models and the migrated schema agree."""
    with pg_engine.connect() as connection:
        ctx = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_all_tables_present(pg_engine):
    with pg_engine.connect() as connection:
        count = connection.execute(
            text(
                "select count(*) from information_schema.tables"
                " where table_schema = 'public' and table_name <> 'alembic_version'"
            )
        ).scalar_one()
    assert count == len(Base.metadata.tables) == 36
