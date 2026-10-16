"""Response schemas of the reference data and libraries (docs/api/openapi.yaml: MuscleGroup, Exercise*, Food*)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

BodyRegion = Literal["upper", "lower", "core"]
Equipment = Literal["none", "home", "gym"]
ExperienceLevel = Literal["beginner", "intermediate", "advanced"]
FoodRole = Literal["protein", "carb", "fat", "vegetable", "fruit", "dairy", "dish", "other"]


class InjuryType(BaseModel):
    id: int
    name: str
    description: str = ""
    avg_healing_time_days: int = 0


class Allergen(BaseModel):
    id: int
    name: str
    description: str = ""


class MuscleGroup(BaseModel):
    id: int
    name: str
    description: str = ""
    image_url: str | None = None
    body_region: BodyRegion


class MuscleGroupRef(BaseModel):
    id: int
    name: str


class FoodCategory(BaseModel):
    id: int
    name: str
    description: str = ""


class ExerciseSummary(BaseModel):
    id: int
    name: str
    main_muscle_group: MuscleGroupRef
    difficulty_level: ExperienceLevel
    equipment: Equipment
    is_compound: bool
    is_bodyweight: bool


class Exercise(ExerciseSummary):
    description: str
    instruction: str
    secondary_muscle_groups: list[MuscleGroupRef]


class ExercisePage(BaseModel):
    items: list[ExerciseSummary]
    total: int
    limit: int
    offset: int


class FoodSummary(BaseModel):
    id: int
    name: str
    calories_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    role: FoodRole
    default_portion_g: int


class Food(FoodSummary):
    categories: list[FoodCategory]
    allergens: list[Allergen]
    is_vegetarian: bool
    is_vegan: bool
    min_portion_g: int
    max_portion_g: int
    portion_step_g: int


class FoodPage(BaseModel):
    items: list[FoodSummary]
    total: int
    limit: int
    offset: int
