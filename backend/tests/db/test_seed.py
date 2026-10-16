"""DB-03: reference seeds load, are idempotent and match docs/algorithms.md section 3."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

SEED = Path(__file__).resolve().parents[3] / "database" / "seed" / "load.py"
TABLES = ("muscle_group", "injury_type", "allergen", "food_category")

# algorithms.md section 3
UPPER = {"chest", "back", "shoulders", "biceps", "triceps"}
LOWER = {"quadriceps", "hamstrings", "glutes", "calves"}
CORE = {"core"}


@pytest.fixture(scope="module")
def loader():
    if not SEED.exists():
        pytest.skip("database/ is not part of this checkout")
    spec = importlib.util.spec_from_file_location("seed_load", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def conn(pg_engine):
    url = pg_engine.url.set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as connection:
        yield connection
        connection.rollback()


def _snapshot(conn) -> dict[str, list[tuple]]:
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in TABLES}  # noqa: S608


def test_loading_twice_gives_identical_data(loader, conn):
    loader.load(conn)
    first = _snapshot(conn)
    loader.load(conn)
    assert _snapshot(conn) == first  # same rows and the same ids: no duplicates, no churn
    assert all(first[t] for t in TABLES)


def test_muscle_groups_match_the_specification(loader, conn):
    loader.load(conn)
    rows = dict(conn.execute("SELECT name, body_region FROM muscle_group").fetchall())
    assert set(rows) == UPPER | LOWER | CORE
    assert {n for n, r in rows.items() if r == "upper"} == UPPER
    assert {n for n, r in rows.items() if r == "lower"} == LOWER
    assert {n for n, r in rows.items() if r == "core"} == CORE


def test_allergens_cover_the_eu_list(loader, conn):
    loader.load(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM allergen")}
    eu14 = {"gluten", "crustaceans", "eggs", "fish", "peanuts", "soy", "milk", "tree nuts", "celery", "mustard",
            "sesame", "sulphites", "lupin", "molluscs"}
    assert eu14 <= names and "lactose" in names


def test_injury_types_have_positive_healing_time(loader, conn):
    loader.load(conn)
    rows = conn.execute("SELECT name, avg_healing_time_days FROM injury_type").fetchall()
    assert len(rows) >= 10 and all(days > 0 for _, days in rows)


def test_reference_data_is_not_duplicated_by_case(loader, conn):
    loader.load(conn)
    for table in TABLES:
        n, distinct = conn.execute(f"SELECT count(*), count(DISTINCT lower(name)) FROM {table}").fetchone()  # noqa: S608
        assert n == distinct, table
