"""Real-time meal suggestions (FR-N5). algorithms.md section 10."""
from __future__ import annotations

from dataclasses import dataclass

from .constants import (SUGGESTION_COUNT, SUGGESTION_IDEAL_SHARE, SUGGESTION_KCAL_OVERSHOOT,
                        SUGGESTION_MIN_REMAINING_KCAL)
from .diet import Food
from .meal_scaling import Macros, macros_for
from .rounding import round_half_up


@dataclass(frozen=True)
class Suggestion:
    kind: str                 # food | planned_meal
    ref_id: int               # food id, or planned meal id
    grams: int | None
    macros: Macros
    score: float


def remaining(daily: Macros, logged: Macros) -> Macros:
    return Macros(daily.kcal - logged.kcal, daily.protein - logged.protein, daily.fat - logged.fat, daily.carbs - logged.carbs)


def _score(c: Macros, ideal: Macros) -> float:
    s = 0.0
    for a, b in ((c.protein, ideal.protein), (c.fat, ideal.fat), (c.carbs, ideal.carbs)):
        s += ((a - b) / b) ** 2 if b > 0 else (a * a if a > 0 else 0.0)
    return s


def suggest(daily: Macros, logged: Macros, foods: list[Food], planned_meals: list[tuple[int, Macros]] | None = None
            ) -> tuple[list[Suggestion], str | None]:
    """`foods` must already be filtered for allergies, exclusions and diet type. Returns (suggestions, message)."""
    rem = remaining(daily, logged)
    if rem.kcal < SUGGESTION_MIN_REMAINING_KCAL:
        return [], "target_reached"
    ideal_kcal = min(rem.kcal, SUGGESTION_IDEAL_SHARE * daily.kcal)
    ideal = rem.scaled(ideal_kcal / rem.kcal)
    limit = rem.kcal * SUGGESTION_KCAL_OVERSHOOT
    cands: list[Suggestion] = []
    for pid, m in planned_meals or []:
        if m.kcal <= limit:
            cands.append(Suggestion("planned_meal", pid, None, m, _score(m, ideal)))
    for f in foods:
        if f.per100.kcal <= 0:
            continue
        g = ideal_kcal / (f.per100.kcal / 100)
        g = int(min(max(round_half_up(g / f.step_g) * f.step_g, f.min_g), f.max_g))
        m = macros_for(f.per100, g)
        if m.kcal <= limit:
            cands.append(Suggestion("food", f.id, g, m, _score(m, ideal)))
    cands.sort(key=lambda s: (s.score, s.kind, s.ref_id))
    return cands[:SUGGESTION_COUNT], None
