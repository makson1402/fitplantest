"""Gram scaling by bounded least squares (FR-P6). algorithms.md section 5.4."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear

from .constants import SCALING_WEIGHTS
from .rounding import round_half_up


@dataclass(frozen=True)
class Macros:
    kcal: float
    protein: float
    fat: float
    carbs: float

    def scaled(self, k: float) -> "Macros":
        return Macros(self.kcal * k, self.protein * k, self.fat * k, self.carbs * k)

    def __add__(self, o: "Macros") -> "Macros":
        return Macros(self.kcal + o.kcal, self.protein + o.protein, self.fat + o.fat, self.carbs + o.carbs)


ZERO = Macros(0, 0, 0, 0)


@dataclass(frozen=True)
class Portionable:
    per100: Macros
    min_g: int
    max_g: int
    step_g: int


def macros_for(per100: Macros, grams: float) -> Macros:
    return per100.scaled(grams / 100)


def scale_meal(foods: list[Portionable], target: Macros) -> tuple[list[int], Macros]:
    A = np.array([[f.per100.kcal, f.per100.protein, f.per100.fat, f.per100.carbs] for f in foods], float).T
    t = np.array([target.kcal, target.protein, target.fat, target.carbs], float)
    w = np.array(SCALING_WEIGHTS, float) / np.maximum(t, 1e-9)
    res = lsq_linear(A * w[:, None], t * w,
                     bounds=([f.min_g / 100 for f in foods], [f.max_g / 100 for f in foods]))
    grams: list[int] = []
    for f, x in zip(foods, res.x):
        g = round_half_up(x * 100 / f.step_g) * f.step_g
        grams.append(int(min(max(g, f.min_g), f.max_g)))
    tot = A @ (np.array(grams) / 100)
    return grams, Macros(*(float(v) for v in tot))
