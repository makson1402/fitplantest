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


# ------------------------------------------------------------------ DB-04: exercises

VALIDATOR = SEED.parents[2] / "scripts" / "validate_seed.py"
EXERCISE_TABLES = {
    "exercise": "SELECT * FROM exercise ORDER BY id",
    "secondary": "SELECT * FROM exercise_secondary_muscle_group ORDER BY exercise_id, muscle_group_id",
    "exclusions": "SELECT * FROM injury_type_excluded_exercise ORDER BY injury_type_id, exercise_id",
}


@pytest.fixture(scope="module")
def validator():
    if not VALIDATOR.exists():
        pytest.skip("scripts/ is not part of this checkout")
    spec = importlib.util.spec_from_file_location("validate_seed", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exercise_seed_is_idempotent(loader, conn):
    loader.load(conn)
    first = {k: conn.execute(q).fetchall() for k, q in EXERCISE_TABLES.items()}
    loader.load(conn)
    assert {k: conn.execute(q).fetchall() for k, q in EXERCISE_TABLES.items()} == first
    assert len(first["exercise"]) >= 100 and first["secondary"] and first["exclusions"]


def test_validation_script_passes(loader, validator, conn):
    loader.load(conn)
    assert validator.violations(conn) == []


def test_every_group_is_trainable_at_every_level_and_equipment(loader, validator, conn):
    loader.load(conn)
    for group, cells in validator.coverage(conn).items():
        assert all(count >= 1 for count in cells.values()), (group, cells)  # no FR-P3 gaps in the seed


def test_secondary_group_never_equals_main_group(loader, conn):
    loader.load(conn)
    bad = conn.execute(
        "SELECT e.name FROM exercise_secondary_muscle_group s JOIN exercise e ON e.id = s.exercise_id"
        " WHERE s.muscle_group_id = e.main_muscle_group_id").fetchall()
    assert bad == []


def test_validator_detects_a_broken_seed(loader, validator, conn):
    loader.load(conn)
    conn.execute("UPDATE exercise SET description = ' ' WHERE name = 'Plank'")
    conn.execute("DELETE FROM exercise WHERE main_muscle_group_id = (SELECT id FROM muscle_group WHERE name = 'calves')")
    problems = validator.violations(conn)
    assert any("Plank" in p for p in problems) and any(p.startswith("calves") for p in problems)
