"""Diet plan generation (FR-P6). algorithms.md section 5."""
from __future__ import annotations

from dataclasses import dataclass, field

from .constants import (DAY_TOLERANCE, DIET_EXTRA_ATTEMPTS, DIET_MAX_ATTEMPTS, DIET_MEAL_CANDIDATES, MEAL_SLOTS,
                        SCALING_WEIGHTS)
from .meal_scaling import ZERO, Macros, Portionable, macros_for, scale_meal
from .nutrition import Targets


@dataclass(frozen=True)
class Food:
    id: int
    role: str                              # protein carb fat vegetable fruit dairy dish other
    per100: Macros
    min_g: int
    max_g: int
    step_g: int
    default_g: int
    meal_types: frozenset[str]
    allergens: frozenset[int] = frozenset()
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_active: bool = True


@dataclass(frozen=True)
class PlannedMealItem:
    food_id: int
    grams: int
    macros: Macros


@dataclass(frozen=True)
class PlannedMeal:
    day_index: int
    meal_type: str
    items: tuple[PlannedMealItem, ...]
    totals: Macros


@dataclass(frozen=True)
class DietPlan:
    meals: tuple[PlannedMeal, ...]


class InsufficientFoods(Exception):
    def __init__(self, missing_roles: list[dict], message: str = "not enough eligible foods"):
        super().__init__(message)
        self.missing_roles = missing_roles


def eligible_foods(foods: list[Food], meal_type: str | None, diet_type: str, user_allergens: set[int],
                   excluded_food_ids: set[int]) -> list[Food]:
    out = []
    for f in foods:
        if not f.is_active or f.id in excluded_food_ids or (f.allergens & user_allergens):
            continue
        if meal_type is not None and meal_type not in f.meal_types:
            continue
        if diet_type == "vegetarian" and not f.is_vegetarian:
            continue
        if diet_type == "vegan" and not f.is_vegan:
            continue
        out.append(f)
    return out


def _roles_for(meal_type: str, day: int, slot: int, has_dish: bool) -> list[tuple[str, ...]]:
    """Each element is a tuple of acceptable roles; one item is chosen per element."""
    dish_day = has_dish and (day - 1) % 3 == 2
    if meal_type == "breakfast":
        return [("protein", "dairy"), ("carb",), ("fruit",), ("fat",)]
    if meal_type in ("lunch", "dinner"):
        if dish_day:
            return [("dish",), ("vegetable",), ("fat",)]
        return [("protein",), ("carb",), ("vegetable",), ("fat",)]
    return [("fruit", "dairy"), ("fat",)]          # snack; fat is optional (see _OPTIONAL)


_OPTIONAL = {("snack", ("fat",))}
GOOD_MEAL_ERROR = 5e-4  # about 1 % off on every macro in the objective of 5.4


def _pick(pool: list[Food], day: int, slot: int, attempt: int, prev_id: int | None) -> Food:
    n = len(pool)
    idx = (day - 1 + 2 * slot + attempt) % n
    if n >= 2 and pool[idx].id == prev_id:
        idx = (idx + 1) % n
    return pool[idx]


def _within(total: Macros, daily: Targets) -> bool:
    t = {"kcal": daily.target_kcal, "protein": daily.protein_g, "fat": daily.fat_g, "carbs": daily.carbs_g}
    v = {"kcal": total.kcal, "protein": total.protein, "fat": total.fat, "carbs": total.carbs}
    return all(abs(v[k] - t[k]) <= DAY_TOLERANCE[k] * t[k] for k in t)


def generate_diet(targets: Targets, meals_per_day: int, foods: list[Food], diet_type: str = "omnivore",
                  user_allergens: set[int] | None = None, excluded_food_ids: set[int] | None = None) -> DietPlan:
    slots = MEAL_SLOTS[meals_per_day]
    allergens, excluded = user_allergens or set(), excluded_food_ids or set()
    pools: dict[str, dict[str, list[Food]]] = {}
    for mt in {s[0] for s in slots}:
        by_role: dict[str, list[Food]] = {}
        for f in sorted(eligible_foods(foods, mt, diet_type, allergens, excluded), key=lambda f: f.id):
            by_role.setdefault(f.role, []).append(f)
        pools[mt] = by_role

    # roles that can never be satisfied -> fail early with a precise message
    missing = []
    for mt, by_role in pools.items():
        for group in _roles_for(mt, 1, 0, False):
            if (mt, group) in _OPTIONAL:
                continue
            if not any(by_role.get(r) for r in group):
                missing.append({"meal_type": mt, "role": "|".join(group)})
    if missing:
        raise InsufficientFoods(missing)

    meals: list[PlannedMeal] = []
    prev: dict[tuple[int, int], int | None] = {}
    daily = Macros(targets.target_kcal, targets.protein_g, targets.fat_g, targets.carbs_g)
    scaled: dict[tuple, tuple[list[int], Macros]] = {}

    def meal_error(total: Macros, target: Macros) -> float:
        """The scaling objective of 5.4 (weighted squared relative deviation) of a scaled meal."""
        t = (target.kcal, target.protein, target.fat, target.carbs)
        v = (total.kcal, total.protein, total.fat, total.carbs)
        return sum(w * ((vi - ti) / max(ti, 1e-9)) ** 2 for w, vi, ti in zip(SCALING_WEIGHTS, v, t))

    def try_day(day: int, attempt: int, allow_dish: bool, candidates: int = 1):
        """One candidate day: choose items by the rotation of 5.3, scale them (5.4). (meals, chosen ids) when the
        totals are within the daily tolerance (5.5), otherwise None.

        With `candidates` > 1 (stage 2) every meal tries that many consecutive rotation offsets and keeps the one
        whose scaled meal is closest to its own target, so a day no longer depends on all meals being lucky."""
        day_meals, chosen_ids = [], {}
        so_far = ZERO
        for i, (mt, share) in enumerate(slots):
            by_role = pools[mt]
            if candidates > 1:
                # stage 2: a meal aims at its share of what is still missing from the day, so the rounding and
                # portion-limit errors of the earlier meals are made up by the later ones
                left = sum(sh for _, sh in slots[i:])
                missing = Macros(daily.kcal - so_far.kcal, daily.protein - so_far.protein, daily.fat - so_far.fat,
                                 daily.carbs - so_far.carbs)
                meal_target = missing.scaled(share / left)
                meal_target = Macros(*(max(v, 0.05 * d) for v, d in zip(
                    (meal_target.kcal, meal_target.protein, meal_target.fat, meal_target.carbs),
                    (daily.kcal * share, daily.protein * share, daily.fat * share, daily.carbs * share))))
            else:
                meal_target = daily.scaled(share)
            groups = _roles_for(mt, day, i, allow_dish and bool(by_role.get("dish")))
            best = None
            for c in range(candidates):
                chosen: list[Food] = []
                ids: dict[tuple[int, int], int] = {}
                for gi, group in enumerate(groups):
                    pool = sorted([f for r in group for f in by_role.get(r, [])], key=lambda f: f.id)
                    if not pool:
                        if (mt, group) in _OPTIONAL:
                            continue
                        return None
                    chosen.append(_pick(pool, day, i + gi, attempt * candidates + c, prev.get((i, gi))))
                    ids[(i, gi)] = chosen[-1].id
                key = (tuple(f.id for f in chosen), round(meal_target.kcal), round(meal_target.protein),
                       round(meal_target.fat), round(meal_target.carbs))  # same items and target: same result
                if key not in scaled:
                    scaled[key] = scale_meal([Portionable(f.per100, f.min_g, f.max_g, f.step_g) for f in chosen],
                                             meal_target)
                grams, tot = scaled[key]
                error = meal_error(tot, meal_target)
                if best is None or error < best[0]:
                    best = (error, chosen, grams, tot, ids)
                if candidates > 1 and error <= GOOD_MEAL_ERROR:
                    break  # close enough on all four macros: no need to try further offsets
            _, chosen, grams, tot, ids = best
            chosen_ids.update(ids)
            items = tuple(PlannedMealItem(f.id, g, macros_for(f.per100, g)) for f, g in zip(chosen, grams))
            day_meals.append(PlannedMeal(day, mt, items, tot))
            so_far = so_far + tot
        total = ZERO
        for m in day_meals:
            total = total + m.totals
        return (day_meals, chosen_ids) if _within(total, targets) else None

    for day in range(1, 8):
        # Stage 1: the 5 attempts of algorithms.md 5.5, unchanged. Stage 2 (amendment, see algorithms.md 5.5):
        # per-meal best of DIET_MEAL_CANDIDATES rotation offsets, and no `dish` item (a composite food has fixed
        # proportions and rarely meets all four macros). Plans found by stage 1 are the same as before.
        found = None
        for attempt in range(DIET_MAX_ATTEMPTS):
            found = try_day(day, attempt, True)
            if found:
                break
        for attempt in range(DIET_EXTRA_ATTEMPTS if not found else 0):
            found = try_day(day, attempt, False, DIET_MEAL_CANDIDATES)
            if found:
                break
        if not found:
            raise InsufficientFoods(
                [], f"day {day}: totals stay outside tolerance after {DIET_MAX_ATTEMPTS + DIET_EXTRA_ATTEMPTS} attempts")
        meals.extend(found[0])
        prev = found[1]
    return DietPlan(tuple(meals))
