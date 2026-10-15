"""Energy needs and macro targets (FR-P4, FR-P5). algorithms.md sections 1-2."""
from __future__ import annotations

from dataclasses import dataclass

from .constants import (FAT_SHARE_OF_KCAL, GOAL_KCAL_FACTOR, KCAL_FLOOR, PROTEIN_G_PER_KG,
                        PROTEIN_MAX_SHARE, SEX_OFFSET)
from .rounding import round_half_up


@dataclass(frozen=True)
class Targets:
    bmr_kcal: float
    tdee_kcal: int
    target_kcal: int
    protein_g: float
    fat_g: float
    carbs_g: float


def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + SEX_OFFSET[sex]


def tdee(sex: str, weight_kg: float, height_cm: float, age: int, pal: float) -> int:
    return int(round_half_up(bmr(sex, weight_kg, height_cm, age) * pal))


def nutrition_targets(sex: str, weight_kg: float, height_cm: float, age: int, pal: float, goal: str) -> Targets:
    t = tdee(sex, weight_kg, height_cm, age, pal)
    kcal = max(int(round_half_up(t * GOAL_KCAL_FACTOR[goal])), KCAL_FLOOR[sex])
    protein = min(PROTEIN_G_PER_KG[goal] * weight_kg, PROTEIN_MAX_SHARE * kcal / 4)
    fat = FAT_SHARE_OF_KCAL[goal] * kcal / 9
    carbs = (kcal - 4 * protein - 9 * fat) / 4
    return Targets(round_half_up(bmr(sex, weight_kg, height_cm, age), 1), t, kcal,
                   round_half_up(protein, 1), round_half_up(fat, 1), round_half_up(carbs, 1))
