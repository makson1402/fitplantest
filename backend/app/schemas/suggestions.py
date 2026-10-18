"""Meal suggestion schemas (docs/api/openapi.yaml: Suggestion, Suggestions)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.diet import Macros
from app.schemas.library import FoodSummary


class Suggestion(BaseModel):
    type: Literal["food", "planned_meal"]
    food: FoodSummary | None = None
    grams: float | None = None
    planned_meal_id: int | None = None
    nutrition: Macros
    score: float


class Suggestions(BaseModel):
    remaining: Macros
    message: Literal["target_reached"] | None = None
    suggestions: list[Suggestion]
