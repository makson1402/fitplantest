from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

import app.db.models  # noqa: F401
from app.db.models.base import Base
from tests.db.conftest import _admin_url

REPO = Path(__file__).resolve().parents[3]


def _catalog(connection) -> dict[str, list]:
    """Everything that defines the schema, from the system catalogs, in a comparable form."""
    queries = {
        "columns": "select table_name, column_name, data_type, udt_name, character_maximum_length, numeric_precision,"
                   " numeric_scale, is_nullable, column_default, is_identity, identity_generation from"
                   " information_schema.columns where table_schema = 'public' and table_name <> 'alembic_version'",
        "constraints": "select conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid) from pg_constraint"
                       " where connamespace = 'public'::regnamespace and conrelid::regclass::text <> 'alembic_version'",
        "indexes": "select tablename, indexname, indexdef from pg_indexes where schemaname = 'public'"
                   " and tablename <> 'alembic_version'",
        "triggers": "select event_object_table, trigger_name, event_manipulation, action_timing, action_statement"
                    " from information_schema.triggers where trigger_schema = 'public'",
        "enums": "select t.typname, array_agg(e.enumlabel order by e.enumsortorder) from pg_type t"
                 " join pg_enum e on e.enumtypid = t.oid group by t.typname",
        "functions": "select proname, pg_get_functiondef(oid) from pg_proc where pronamespace = 'public'::regnamespace",
    }
    return {name: sorted(map(tuple, connection.execute(text(q)).fetchall()), key=repr) for name, q in queries.items()}


def test_migrated_schema_equals_the_reviewed_sql(pg_engine):
    """docs/database/schema_postgres.sql is the reviewed schema. Applying it to an empty database must give exactly
    what `alembic upgrade head` gives (tables, columns, constraints, indexes, triggers, enums, functions)."""
    docs = REPO / "docs" / "database" / "schema_postgres.sql"
    if not docs.exists():
        pytest.skip("docs/ is not part of this checkout")
    admin = _admin_url()
    admin_engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    name = f"fitplan_docs_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        reference = create_engine(admin.set(database=name))
        with reference.begin() as c:
            c.exec_driver_sql(docs.read_text(encoding="utf-8").replace("%", "%%"))
        with reference.connect() as c:
            expected = _catalog(c)
        with pg_engine.connect() as c:
            actual = _catalog(c)
        reference.dispose()
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin_engine.dispose()
    for part in expected:
        assert actual[part] == expected[part], f"{part} differ between schema_postgres.sql and the migrations"


def test_migration_0002_widens_pal_and_keeps_the_check(pg_engine):
    with pg_engine.connect() as c:
        row = c.execute(text(
            "select numeric_precision, numeric_scale from information_schema.columns"
            " where table_name = 'user_profile' and column_name = 'activity_level_pal'")).one()
        check = c.execute(text(
            "select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'user_profile'::regclass"
            " and pg_get_constraintdef(oid) like '%activity_level_pal%'")).scalar_one()
    assert tuple(row) == (4, 3) and "1.20" in check and "2.40" in check


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
