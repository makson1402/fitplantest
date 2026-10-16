"""B-12 'done when': daily kcal and macros within the tolerance for every goal; no allergen is ever selected.

Runs the generator on the SEEDED food database. Plans are checked against rules written here from algorithms.md 5.1,
5.2, 5.3 and 5.5, not with the helpers of the code under test.
"""
from __future__ import annotations

import itertools
import os

import pytest
from sqlalchemy import text

from app.domain.constants import DAY_TOLERANCE, MEAL_SLOTS
from app.domain.diet import Food, InsufficientFoods, generate_diet
from app.domain.meal_scaling import Macros
from app.domain.nutrition import nutrition_targets

PROFILES = {  # sex, kg, cm, age, PAL
    "male80": ("male", 80, 180, 30, 1.55), "female55": ("female", 55, 160, 25, 1.375),
    "heavy": ("male", 120, 185, 35, 1.375), "small": ("female", 48, 150, 60, 1.2),
}
ALL_GOALS = ("weight_loss", "muscle_gain", "strength", "maintenance", "general_fitness", "endurance")
# The goals with the most different targets (lowest kcal / highest protein, highest kcal, highest carbs, middle) keep
# the default run short; FULL_DIET_MATRIX=1 runs all six.
GOALS = ALL_GOALS if os.environ.get("FULL_DIET_MATRIX") else ("weight_loss", "muscle_gain", "endurance", "maintenance")
DIETS = ("omnivore", "vegetarian", "vegan")
ROLES = {  # algorithms.md 5.3 (a lunch/dinner dish replaces protein + carb; a snack fat is optional)
    "breakfast": [{"protein", "dairy"}, {"carb"}, {"fruit"}, {"fat"}],
    "lunch": [{"protein"}, {"carb"}, {"vegetable"}, {"fat"}],
    "dinner": [{"protein"}, {"carb"}, {"vegetable"}, {"fat"}],
    "snack": [{"fruit", "dairy"}, {"fat"}],
}


@pytest.fixture(scope="module")
def library(seeded_engine):
    with seeded_engine.connect() as c:
        allergens: dict[int, set[int]] = {}
        for food_id, allergen_id in c.execute(text("select food_item_id, allergen_id from food_item_allergen")):
            allergens.setdefault(food_id, set()).add(allergen_id)
        foods = [
            Food(r[0], r[1], Macros(float(r[2]), float(r[3]), float(r[4]), float(r[5])), r[6], r[7], r[8], r[9],
                 frozenset(r[10]), frozenset(allergens.get(r[0], ())), r[11], r[12], r[13])
            for r in c.execute(text(
                "select id, role::text, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g,"
                " min_portion_g, max_portion_g, portion_step_g, default_portion_g, suitable_meal_types::text[],"
                " is_vegetarian, is_vegan, is_active from food_item order by id"))]
        allergen_ids = {name: i for i, name in c.execute(text("select id, name from allergen"))}
    return foods, allergen_ids


def _check(plan, targets, meals_per_day, foods_by_id, diet, allergens, excluded):
    slots = MEAL_SLOTS[meals_per_day]
    daily = {"kcal": targets.target_kcal, "protein": targets.protein_g, "fat": targets.fat_g, "carbs": targets.carbs_g}
    assert len(plan.meals) == 7 * meals_per_day
    for day in range(1, 8):
        meals = [m for m in plan.meals if m.day_index == day]
        assert [m.meal_type for m in meals] == [mt for mt, _ in slots]  # 5.1: slot types in order
        for key, limit in DAY_TOLERANCE.items():  # 5.5: the tolerances are exactly the specified ones
            total = sum(getattr(m.totals, key) for m in meals)
            assert abs(total / daily[key] - 1) <= limit + 1e-9, (day, key, total, daily[key])
        for meal in meals:
            ids = [i.food_id for i in meal.items]
            assert len(ids) == len(set(ids))  # a food appears once in a meal (primary key of meal_food_item)
            for item in meal.items:
                f = foods_by_id[item.food_id]
                assert f.is_active and not (f.allergens & allergens) and item.food_id not in excluded  # 5.2
                assert diet == "omnivore" or (f.is_vegetarian if diet == "vegetarian" else f.is_vegan)
                assert meal.meal_type in f.meal_types
                assert f.min_g <= item.grams <= f.max_g and item.grams % f.step_g == 0  # 5.4 bounds and step
            roles = [foods_by_id[i].role for i in ids]
            if "dish" in roles:  # a dish replaces protein + carb at lunch/dinner
                assert meal.meal_type in ("lunch", "dinner") and sorted(roles) == ["dish", "fat", "vegetable"]
            else:
                needed = ROLES[meal.meal_type]
                assert len(roles) in (len(needed), len(needed) - 1 if meal.meal_type == "snack" else len(needed))
                for acceptable, role in zip(needed, roles, strict=False):
                    assert role in acceptable, (meal.meal_type, roles)


def test_typical_users_always_get_a_plan(library):
    """No allergies: every goal, diet type and number of meals works for four very different bodies."""
    foods, _ = library
    by_id = {f.id: f for f in foods}
    for (name, profile), goal, diet, mpd in itertools.product(PROFILES.items(), GOALS, DIETS, (3, 4, 5)):
        targets = nutrition_targets(*profile, goal)
        try:
            plan = generate_diet(targets, mpd, foods, diet)
        except InsufficientFoods as exc:  # pragma: no cover - failure message is the point
            pytest.fail(f"{name} {goal} {diet} {mpd} meals: {exc}")
        _check(plan, targets, mpd, by_id, diet, set(), set())


@pytest.mark.parametrize("allergen_names", [("gluten",), ("milk", "lactose"), ("peanuts", "tree nuts")])
def test_allergens_are_never_selected(library, allergen_names):
    foods, allergen_ids = library
    by_id = {f.id: f for f in foods}
    allergens = {allergen_ids[n] for n in allergen_names}
    produced = failed = 0
    for name, goal, diet, mpd in itertools.product(
        ("male80", "small"), ("weight_loss", "muscle_gain"), DIETS, (3, 5)
    ):
        targets = nutrition_targets(*PROFILES[name], goal)
        try:
            plan = generate_diet(targets, mpd, foods, diet, allergens, set())
        except InsufficientFoods:
            failed += 1
            continue
        produced += 1
        _check(plan, targets, mpd, by_id, diet, allergens, set())
    assert produced > 0 and failed <= 0.2 * (produced + failed), (allergen_names, produced, failed)


def test_excluded_foods_are_never_selected(library):
    foods, _ = library
    by_id = {f.id: f for f in foods}
    chicken = next(f.id for f in foods if f.role == "protein" and f.per100.protein > 30 and f.per100.kcal < 200)
    rice = next(f.id for f in foods if f.role == "carb" and 120 < f.per100.kcal < 140)
    banana = next(f.id for f in foods if f.role == "fruit" and 85 < f.per100.kcal < 95)
    excluded = {chicken, rice, banana}
    targets = nutrition_targets(*PROFILES["male80"], "muscle_gain")
    plan = generate_diet(targets, 4, foods, "omnivore", set(), excluded)
    _check(plan, targets, 4, by_id, "omnivore", set(), excluded)
    assert not excluded & {i.food_id for m in plan.meals for i in m.items}


def test_impossible_requests_are_reported_not_faked(library):
    """Every protein food excluded: nothing can fill the protein role, and the answer names it."""
    foods, _ = library
    targets = nutrition_targets(*PROFILES["male80"], "maintenance")
    excluded = {f.id for f in foods if f.role == "protein"}
    with pytest.raises(InsufficientFoods) as raised:
        generate_diet(targets, 3, foods, "omnivore", set(), excluded)
    assert {"meal_type": "lunch", "role": "protein"} in raised.value.missing_roles
