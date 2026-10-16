"""Validate the seed data and report exercise coverage (DB-04) and food data (DB-05).

    cd backend && uv run python ../scripts/validate_seed.py            # check, exit 1 on a violation
    cd backend && uv run python ../scripts/validate_seed.py --report ../docs/database/exercise_coverage.md

Coverage cell = number of exercises a user with that experience level and equipment can do for the muscle group
(`difficulty_level <= level` and `equipment <= tier`, docs/algorithms.md 4.2), ignoring injuries.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("beginner", "intermediate", "advanced")
TIERS = ("none", "home", "gym")
MIN_PER_GROUP = 8  # docs/agents/data.md: at least 8 exercises per main muscle group
MIN_EXCLUSIONS_PER_INJURY = 5
MIN_FOODS = 150  # docs/agents/data.md
MIN_CHOICES_PER_ROLE = 2  # the diet generator rotates items (algorithms.md 5.3); one item gives no variety
KCAL_TOLERANCE = 0.12  # |kcal - (4P + 9F + 4C)| <= max(12 % of kcal, 15 kcal): fibre explains the rest
KCAL_ABS_TOLERANCE = 15
FOOD101_LABELS = ROOT / "docs" / "database" / "food101_labels.txt"
FOOD101_UNMAPPED = ROOT / "database" / "seed" / "food101_unmapped.txt"
ANIMAL_ALLERGENS = {"milk", "lactose", "eggs", "fish", "crustaceans", "molluscs"}  # never in a vegan food
MEAT_ALLERGENS = {"fish", "crustaceans", "molluscs"}  # never in a vegetarian food
# role sets needed per meal type (docs/algorithms.md 5.3)
MEAL_ROLES = {
    "breakfast": [("protein", "dairy"), ("carb",), ("fruit",), ("fat",)],
    "lunch": [("protein",), ("carb",), ("vegetable",), ("fat",)],
    "dinner": [("protein",), ("carb",), ("vegetable",), ("fat",)],
    "snack": [("fruit", "dairy")],
}
DIETS = {"omnivore": "true", "vegetarian": "is_vegetarian", "vegan": "is_vegan"}


def _loader():
    spec = importlib.util.spec_from_file_location("seed_load", ROOT / "database" / "seed" / "load.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def coverage(conn: psycopg.Connection) -> dict[str, dict[tuple[str, str], int]]:
    """{group: {(level, tier): eligible exercise count}}."""
    rows = conn.execute(
        "SELECT mg.name, e.difficulty_level::text, e.equipment::text FROM exercise e "
        "JOIN muscle_group mg ON mg.id = e.main_muscle_group_id"
    ).fetchall()
    groups = [r[0] for r in conn.execute("SELECT name FROM muscle_group ORDER BY id").fetchall()]
    result: dict[str, dict[tuple[str, str], int]] = {g: {} for g in groups}
    for group in groups:
        for li, level in enumerate(LEVELS):
            for ti, tier in enumerate(TIERS):
                result[group][(level, tier)] = sum(
                    1 for g, lv, eq in rows if g == group and LEVELS.index(lv) <= li and TIERS.index(eq) <= ti
                )
    return result


def _label_file(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def food_violations(conn: psycopg.Connection) -> list[str]:
    problems: list[str] = []
    n = conn.execute("SELECT count(*) FROM food_item WHERE is_active").fetchone()[0]
    if n < MIN_FOODS:
        problems.append(f"only {n} active foods, need at least {MIN_FOODS}")
    for name, kcal, p, f, c in conn.execute(
        "SELECT name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g FROM food_item"
    ).fetchall():
        atwater = 4 * p + 9 * f + 4 * c
        if abs(float(kcal) - float(atwater)) > max(KCAL_TOLERANCE * float(kcal), KCAL_ABS_TOLERANCE):
            problems.append(f"food '{name}': {kcal} kcal but 4P+9F+4C = {float(atwater):.0f}")
    for (name,) in conn.execute(
        "SELECT name FROM food_item WHERE min_portion_g % portion_step_g <> 0 OR max_portion_g % portion_step_g <> 0"
        " OR default_portion_g % portion_step_g <> 0"
    ).fetchall():
        problems.append(f"food '{name}': portion bounds must be multiples of portion_step_g (the scaler rounds)")
    for diet, flag in DIETS.items():
        for meal, role_sets in MEAL_ROLES.items():
            for roles in role_sets:
                count = conn.execute(
                    f"SELECT count(*) FROM food_item WHERE is_active AND {flag} AND role::text = ANY(%s)"  # noqa: S608
                    " AND %s::meal_type_t = ANY(suitable_meal_types)", (list(roles), meal)).fetchone()[0]
                if count < MIN_CHOICES_PER_ROLE:
                    problems.append(f"{diet} {meal}: only {count} food(s) for role {'/'.join(roles)}")
    for (name,) in conn.execute(
        "SELECT a.name FROM allergen a WHERE NOT EXISTS (SELECT 1 FROM food_item_allergen x WHERE x.allergen_id = a.id)"
    ).fetchall():
        problems.append(f"allergen '{name}' is not attached to any food")
    for name, vegan, vegetarian, allergens in conn.execute(
        "SELECT fi.name, fi.is_vegan, fi.is_vegetarian, array_agg(a.name) FROM food_item fi "
        "JOIN food_item_allergen x ON x.food_item_id = fi.id JOIN allergen a ON a.id = x.allergen_id GROUP BY 1, 2, 3"
    ).fetchall():
        if vegan and ANIMAL_ALLERGENS & set(allergens):
            problems.append(f"food '{name}' is marked vegan but has allergens {sorted(allergens)}")
        if vegetarian and MEAT_ALLERGENS & set(allergens):
            problems.append(f"food '{name}' is marked vegetarian but has allergens {sorted(allergens)}")
    # Food-101: every label is mapped or listed as intentionally unmapped, never both
    labels = set(_label_file(FOOD101_LABELS)) if FOOD101_LABELS.exists() else set()
    unmapped = set(_label_file(FOOD101_UNMAPPED)) if FOOD101_UNMAPPED.exists() else set()
    mapped = {r[0] for r in conn.execute("SELECT recognition_label FROM food_item WHERE recognition_label IS NOT NULL")}
    if labels:
        problems += [f"Food-101 label '{x}' is neither mapped nor unmapped" for x in sorted(labels - mapped - unmapped)]
        problems += [f"Food-101 label '{x}' is both mapped and unmapped" for x in sorted(mapped & unmapped)]
        problems += [f"recognition_label '{x}' is not a Food-101 label" for x in sorted(mapped - labels)]
        problems += [f"unmapped entry '{x}' is not a Food-101 label" for x in sorted(unmapped - labels)]
    return problems


def violations(conn: psycopg.Connection) -> list[str]:
    problems: list[str] = []
    cov = coverage(conn)
    totals = dict(conn.execute(
        "SELECT mg.name, count(e.id) FROM muscle_group mg LEFT JOIN exercise e ON e.main_muscle_group_id = mg.id "
        "GROUP BY mg.name").fetchall())
    for group, n in sorted(totals.items()):
        if n < MIN_PER_GROUP:
            problems.append(f"{group}: {n} exercises, need at least {MIN_PER_GROUP}")
    for group, cells in cov.items():
        if cells[("beginner", "none")] == 0:  # a bodyweight beginner must be able to train every group
            problems.append(f"{group}: no exercise for beginner/none")
    empty = conn.execute(
        "SELECT name FROM exercise WHERE btrim(description) = '' OR btrim(instruction) = ''").fetchall()
    problems += [f"exercise '{n}': empty description or instruction" for (n,) in empty]
    dup = conn.execute(
        "SELECT lower(name) FROM exercise GROUP BY lower(name) HAVING count(*) > 1").fetchall()
    problems += [f"duplicate exercise name '{n}'" for (n,) in dup]
    sparse = conn.execute(
        "SELECT it.name, count(x.exercise_id) FROM injury_type it "
        "LEFT JOIN injury_type_excluded_exercise x ON x.injury_type_id = it.id GROUP BY it.name "
        "HAVING count(x.exercise_id) < %s", (MIN_EXCLUSIONS_PER_INJURY,)).fetchall()
    problems += [f"injury type '{n}': only {c} excluded exercises" for n, c in sparse]
    return problems + food_violations(conn)


def report(conn: psycopg.Connection) -> str:
    cov = coverage(conn)
    total = conn.execute("SELECT count(*) FROM exercise").fetchone()[0]
    header = ["muscle group"] + [f"{lv[:3]}/{t}" for lv in LEVELS for t in TIERS]
    lines = [
        "# Exercise coverage (DB-04)",
        "",
        f"Generated by `scripts/validate_seed.py --report`. {total} exercises. Each cell is the number of exercises",
        "a user with that level (beg/int/adv) and equipment (none/home/gym) can do for the group, injuries ignored",
        "(`docs/algorithms.md` 4.2). `0` is a gap: FR-P3 then applies (`insufficient_exercises`).",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] + ["---:"] * 9) + " |",
    ]
    gaps = []
    for group, cells in cov.items():
        row = [cells[(lv, t)] for lv in LEVELS for t in TIERS]
        lines.append(f"| {group} | " + " | ".join(str(v) for v in row) + " |")
        gaps += [f"{group} at {lv}/{t}" for lv in LEVELS for t in TIERS if cells[(lv, t)] == 0]
    lines += ["", "## Gaps", ""]
    none = "None: every muscle group has at least one exercise for every level and equipment tier."
    lines += [f"- {g}" for g in gaps] if gaps else [none]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, help="write the coverage report (Markdown) to this path")
    args = parser.parse_args()
    with psycopg.connect(_loader().database_dsn()) as conn:
        if args.report:
            args.report.write_text(report(conn), encoding="utf-8", newline="\n")
            print(f"wrote {args.report}")
        problems = violations(conn)
    for problem in problems:
        print(f"FAIL: {problem}")
    print("seed validation: " + ("FAILED" if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
