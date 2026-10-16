"""Nutrition log schemas (docs/api/openapi.yaml: NutritionLog*, DailySummary)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.diet import Macros, MealType
from app.schemas.library import FoodSummary


class NutritionLogItemInput(BaseModel):
    food_item_id: int
    grams: float = Field(gt=0, le=2000, allow_inf_nan=False)


class NutritionLogInput(BaseModel):
    # Optional; the default is never validated: an absent field is None, an explicit `null` is a 422.
    client_uuid: UUID = Field(default=None)  # type: ignore[assignment]
    log_date: date
    meal_type: MealType
    items: list[NutritionLogItemInput] = Field(min_length=1)
    hunger_level_before: int | None = Field(default=None, ge=1, le=10)
    hunger_level_after: int | None = Field(default=None, ge=1, le=10)
    planned_meal_id: int | None = None


class NutritionLogUpdate(BaseModel):
    """PATCH body (contract: at least one property). Only the fields the client sent change; the hunger levels may
    be cleared with `null`, the items may not."""

    model_config = ConfigDict(json_schema_extra={"minProperties": 1})

    items: list[NutritionLogItemInput] = Field(default=None, min_length=1)  # type: ignore[assignment]
    hunger_level_before: int | None = Field(default=None, ge=1, le=10)
    hunger_level_after: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def at_least_one_field(self) -> NutritionLogUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class NutritionLogItem(BaseModel):
    food: FoodSummary
    grams: float
    nutrition: Macros


class NutritionLog(BaseModel):
    id: int
    client_uuid: UUID
    log_date: date
    meal_type: MealType
    meal_photo_url: str | None = None
    items: list[NutritionLogItem]
    totals: Macros
    hunger_level_before: int | None = None
    hunger_level_after: int | None = None
    planned_meal_id: int | None = None
    recognition_id: int | None = None
    logged_at: datetime
    updated_at: datetime


class NutritionLogPage(BaseModel):
    items: list[NutritionLog]
    total: int
    limit: int
    offset: int


class DailySummary(BaseModel):
    date: date
    targets: Macros | None = Field(default=None, description="Null without an active diet plan")
    totals: Macros
    remaining: Macros | None = None
    logs_count: int
    avg_hunger_before: float | None = None
    avg_hunger_after: float | None = None
