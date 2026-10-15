"""Diet plan generation (FR-P6). algorithms.md section 5."""
from __future__ import annotations

from dataclasses import dataclass, field

from .constants import DAY_TOLERANCE, DIET_MAX_ATTEMPTS, MEAL_SLOTS
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
    for day in range(1, 8):
        for attempt in range(DIET_MAX_ATTEMPTS):
            day_meals, chosen_ids = [], {}
            ok = True
            for i, (mt, share) in enumerate(slots):
                by_role = pools[mt]
                chosen: list[Food] = []
                for gi, group in enumerate(_roles_for(mt, day, i, bool(by_role.get("dish")))):
                    pool = sorted([f for r in group for f in by_role.get(r, [])], key=lambda f: f.id)
                    if not pool:
                        if (mt, group) in _OPTIONAL:
                            continue
                        ok = False
                        break
                    chosen.append(_pick(pool, day, i + gi, attempt, prev.get((i, gi))))
                    chosen_ids[(i, gi)] = chosen[-1].id
                if not ok:
                    break
                grams, tot = scale_meal([Portionable(f.per100, f.min_g, f.max_g, f.step_g) for f in chosen],
                                        daily.scaled(share))
                items = tuple(PlannedMealItem(f.id, g, macros_for(f.per100, g)) for f, g in zip(chosen, grams))
                day_meals.append(PlannedMeal(day, mt, items, tot))
            if ok:
                total = ZERO
                for m in day_meals:
                    total = total + m.totals
                if _within(total, targets):
                    meals.extend(day_meals)
                    prev = chosen_ids
                    break
        else:
            raise InsufficientFoods([], f"day {day}: totals stay outside tolerance after {DIET_MAX_ATTEMPTS} attempts")
    return DietPlan(tuple(meals))
