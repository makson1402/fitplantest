"""Profile, injury, allergy and excluded-food schemas (docs/api/openapi.yaml: ProfileInput, Profile, Injury*)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.ids import Id32
from app.schemas.library import Allergen, Equipment, ExperienceLevel, FoodSummary

Sex = Literal["male", "female", "other"]
Goal = Literal["weight_loss", "muscle_gain", "strength", "maintenance", "general_fitness", "endurance"]
Severity = Literal["mild", "moderate", "severe"]

# Ranges: docs/algorithms.md section 0. `allow_inf_nan=False` keeps NaN/Infinity out of the database.
Weight = Annotated[float, Field(ge=30, le=300, allow_inf_nan=False)]


class ProfileInput(BaseModel):
    age: int = Field(ge=16, le=100)
    sex: Sex
    weight_kg: Weight
    height_cm: int = Field(ge=120, le=250)
    activity_level_pal: float = Field(ge=1.2, le=2.4, allow_inf_nan=False,
                                      description="App offers 1.2, 1.375, 1.55, 1.725, 1.9")
    goal: Goal
    target_weight_kg: Weight | None = None
    experience_level: ExperienceLevel
    equipment: Equipment


class Profile(ProfileInput):
    tdee_kcal: int
    updated_at: datetime


class InjuryInput(BaseModel):
    injury_type_id: Id32
    affected_muscle_group_id: Id32
    severity: Severity
    start_date: date
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=500)


class InjuryUpdate(BaseModel):
    """PATCH body. The defaults are never validated or used: only fields the client sent are applied, so an
    explicit `severity: null` is a 422 (the contract's type is not nullable) while `notes: null` clears the note."""

    severity: Severity = None  # type: ignore[assignment]
    is_active: bool = None  # type: ignore[assignment]
    notes: str | None = Field(default=None, max_length=500)


class Injury(InjuryInput):
    id: int
    injury_type_name: str
    affected_muscle_group_name: str


class AllergyList(BaseModel):
    allergen_ids: list[Id32]


class ExcludedFoodList(BaseModel):
    food_item_ids: list[Id32]


__all__ = ["Allergen", "AllergyList", "ExcludedFoodList", "FoodSummary", "Injury", "InjuryInput", "InjuryUpdate",
           "Profile", "ProfileInput"]
