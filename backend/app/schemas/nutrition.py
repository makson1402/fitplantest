"""Nutrition schemas (docs/api/openapi.yaml: NutritionTargets)."""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.profile import Goal


class NutritionTargets(BaseModel):
    bmr_kcal: float
    tdee_kcal: int
    target_kcal: int
    protein_g: float
    fat_g: float
    carbs_g: float
    goal: Goal
