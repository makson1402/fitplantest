"""Diet plan schemas (docs/api/openapi.yaml: GenerateDietPlanRequest, DietPlan, PlannedMeal, PlannedMealItem)."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.library import FoodSummary
from app.schemas.profile import Goal
from app.schemas.training import PlanStatus

DietType = Literal["omnivore", "vegetarian", "vegan"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class Macros(BaseModel):
    kcal: float
    protein: float = Field(description="grams")
    fat: float = Field(description="grams")
    carbs: float = Field(description="grams")


class GenerateDietPlanRequest(BaseModel):
    meals_per_day: int = Field(ge=3, le=5)
    # Optional; the defaults are never validated: an absent field is None, an explicit `null` is a 422.
    diet_type: DietType = None  # type: ignore[assignment]
    dietary_restrictions: str = Field(default=None, max_length=500,  # type: ignore[assignment]
                                      description="Free-text note shown with the plan")


class PlannedMealItem(BaseModel):
    food: FoodSummary
    grams: float


class PlannedMeal(BaseModel):
    id: int
    day_index: int = Field(ge=1, le=7)
    meal_type: MealType
    meal_order: int
    scheduled_time: time | None = None
    planned: Macros
    items: list[PlannedMealItem]


class DietPlan(BaseModel):
    id: int
    name: str
    goal: Goal
    diet_type: DietType
    meals_per_day: int
    status: PlanStatus
    daily_calorie_target: int
    protein_target_g: float
    fat_target_g: float
    carbs_target_g: float
    dietary_restrictions: str = ""
    generated_at: datetime
    start_date: date | None = None
    end_date: date | None = None
    meals: list[PlannedMeal]
