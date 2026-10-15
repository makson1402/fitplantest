"""Initial schema (task DB-01).

Runs the DDL of docs/database/schema_postgres.sql (copied to alembic/sql/ so the backend image is
self-contained). Keeping the SQL file as the single source of truth guarantees the migrated schema is
exactly the reviewed schema, including triggers, partial indexes and CHECK constraints that
SQLAlchemy models do not describe. Later migrations are ordinary Alembic operations.

Revision ID: 0001
Revises:
"""
import re
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_initial_schema.sql"


def upgrade() -> None:
    op.execute(_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Drop exactly what the DDL created (the schema also holds alembic_version, so it cannot be dropped).
    ddl = _SQL.read_text(encoding="utf-8")
    for table in reversed(re.findall(r"^CREATE TABLE (\w+)", ddl, flags=re.M)):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
    for enum in re.findall(r"^CREATE TYPE (\w+)", ddl, flags=re.M):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
