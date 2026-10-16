"""The stage-2 search of the diet generator (amendment to algorithms.md 5.5, task B-12)."""
from __future__ import annotations

import pytest

import app.domain.diet as diet
from app.domain.diet import Food, InsufficientFoods, generate_diet
from app.domain.meal_scaling import Macros
from app.domain.nutrition import nutrition_targets
from tests.domain.test_generators import foods

TARGETS = nutrition_targets("male", 80, 180, 25, 1.55, "maintenance")


def unbalanced_dish() -> Food:
    """A composite food with fixed, fatty proportions: a dish day built around it cannot meet the macros."""
    return Food(50, "dish", Macros(520, 3, 42, 30), 100, 400, 25, 250, frozenset({"lunch", "dinner"}),
                frozenset(), True, False)


@pytest.mark.parametrize("meals_per_day", [3, 4, 5])
def test_plans_found_by_the_first_five_attempts_are_unchanged(monkeypatch, meals_per_day):
    """Stage 2 only runs when stage 1 fails: with it disabled the same plan comes out."""
    with_stage_two = generate_diet(TARGETS, meals_per_day, foods())
    monkeypatch.setattr(diet, "DIET_EXTRA_ATTEMPTS", 0)
    try:
        stage_one_only = generate_diet(TARGETS, meals_per_day, foods())
    except InsufficientFoods:
        pytest.skip("this fixture needs stage 2 for some day")
    assert with_stage_two == stage_one_only


def test_stage_two_rescues_a_dish_day(monkeypatch):
    catalog = [*foods(), unbalanced_dish()]
    monkeypatch.setattr(diet, "DIET_EXTRA_ATTEMPTS", 0)
    with pytest.raises(InsufficientFoods, match="day 3"):  # the dish day of the rotation cannot be satisfied
        generate_diet(TARGETS, 3, catalog)
    monkeypatch.undo()

    plan = generate_diet(TARGETS, 3, catalog)
    assert len(plan.meals) == 21
    for day in range(1, 8):
        total = sum(m.totals.kcal for m in plan.meals if m.day_index == day)
        assert abs(total / TARGETS.target_kcal - 1) <= 0.05, day  # the tolerance of 5.5 is not relaxed
        protein = sum(m.totals.protein for m in plan.meals if m.day_index == day)
        assert abs(protein / TARGETS.protein_g - 1) <= 0.10, day
    day3 = [i.food_id for m in plan.meals if m.day_index == 3 for i in m.items]
    assert 50 not in day3  # the fallback day uses the standard composition


def test_generation_is_deterministic():
    catalog = [*foods(), unbalanced_dish()]
    assert generate_diet(TARGETS, 4, catalog) == generate_diet(TARGETS, 4, catalog)


def test_every_day_stays_within_the_tolerances_of_the_specification():
    tolerance = {"kcal": 0.05, "protein": 0.10, "fat": 0.15, "carbs": 0.10}
    daily = {"kcal": TARGETS.target_kcal, "protein": TARGETS.protein_g, "fat": TARGETS.fat_g, "carbs": TARGETS.carbs_g}
    for meals_per_day in (3, 4, 5):
        plan = generate_diet(TARGETS, meals_per_day, [*foods(), unbalanced_dish()])
        for day in range(1, 8):
            for key, limit in tolerance.items():
                total = sum(getattr(m.totals, key) for m in plan.meals if m.day_index == day)
                assert abs(total / daily[key] - 1) <= limit + 1e-9, (meals_per_day, day, key)


def test_failure_message_states_the_attempt_budget(monkeypatch):
    light = [f if f.role != "carb" else Food(f.id, f.role, Macros(80, 2, 0.2, 18), f.min_g, 450, 5, 150, f.meal_types)
             for f in foods()]
    with pytest.raises(InsufficientFoods) as raised:
        generate_diet(TARGETS, 3, light)
    assert f"after {diet.DIET_MAX_ATTEMPTS + diet.DIET_EXTRA_ATTEMPTS} attempts" in str(raised.value)
