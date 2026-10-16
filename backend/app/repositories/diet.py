"""Diet plans of one user (B-12): plan, planned meals and their foods, with the plan lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Protocol

from app.repositories.library import FoodRecord


@dataclass
class NewMealItem:
    food_item_id: int
    grams: float


@dataclass
class NewMeal:
    day_index: int
    meal_type: str
    meal_order: int
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float
    items: list[NewMealItem]


@dataclass
class MealItemRecord:
    food: FoodRecord
    grams: Decimal


@dataclass
class MealRecord:
    id: int
    day_index: int
    meal_type: str
    meal_order: int
    scheduled_time: time | None
    planned_calories: Decimal
    planned_protein_g: Decimal
    planned_fat_g: Decimal
    planned_carbs_g: Decimal
    items: list[MealItemRecord] = field(default_factory=list)


@dataclass
class DietPlanRecord:
    id: int
    user_id: int
    name: str
    goal: str
    diet_type: str
    meals_per_day: int
    status: str
    daily_calorie_target: int
    protein_target_g: Decimal
    fat_target_g: Decimal
    carbs_target_g: Decimal
    dietary_restrictions: str
    generated_at: datetime
    start_date: date | None
    end_date: date | None
    meals: list[MealRecord] = field(default_factory=list)


class DietRepository(Protocol):
    async def delete_draft(self, user_id: int) -> None: ...

    async def create_plan(self, user_id: int, *, name: str, goal: str, diet_type: str, meals_per_day: int,
                          daily_calorie_target: int, protein_target_g: float, fat_target_g: float,
                          carbs_target_g: float, dietary_restrictions: str, meals: list[NewMeal]) -> int:
        """Insert a draft plan with its meals; returns the plan id."""
        ...

    async def get_plan(self, user_id: int, plan_id: int) -> DietPlanRecord | None:
        """None when it does not exist or belongs to another user."""
        ...

    async def get_plan_by_status(self, user_id: int, status: str) -> DietPlanRecord | None: ...
    async def archive_active(self, user_id: int) -> None: ...
    async def activate(self, user_id: int, plan_id: int, start_date: date, end_date: date) -> None: ...
