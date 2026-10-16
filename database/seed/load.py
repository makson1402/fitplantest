"""Idempotent seed loader (DB-03).

Runs every `NNN_*.sql` file of this directory in name order, inside one transaction. All seed files use
`INSERT ... ON CONFLICT DO UPDATE`, so running the loader twice leaves the same data.

    cd backend && uv run python ../database/seed/load.py

The database comes from DATABASE_URL or POSTGRES_* (process environment or the repository `.env`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

SEED_DIR = Path(__file__).resolve().parent
ROOT = SEED_DIR.parents[1]


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    values.update(os.environ)
    return values


def database_dsn() -> str:
    env = _env()
    if url := env.get("DATABASE_URL"):
        # SQLAlchemy-style driver suffixes are not understood by libpq.
        scheme, _, rest = url.partition("://")
        return f"{scheme.split('+')[0]}://{rest}"
    return "host={h} port={p} dbname={d} user={u} password={w}".format(
        h=env.get("POSTGRES_HOST", "localhost"), p=env.get("POSTGRES_PORT", "5432"), d=env["POSTGRES_DB"],
        u=env["POSTGRES_USER"], w=env["POSTGRES_PASSWORD"],
    )


def seed_files() -> list[Path]:
    return sorted(SEED_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def load(connection: psycopg.Connection) -> list[str]:
    """Apply all seed files on an open connection (the caller commits). Returns the applied file names."""
    applied = []
    for path in seed_files():
        connection.execute(path.read_text(encoding="utf-8"))
        applied.append(path.name)
    return applied


def main() -> int:
    with psycopg.connect(database_dsn()) as connection:
        applied = load(connection)
        connection.commit()
        for table in ("muscle_group", "injury_type", "allergen", "food_category", "exercise", "food_item"):
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
            print(f"{table}: {count}")
    print(f"applied {len(applied)} seed file(s): {', '.join(p for p in applied)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
