"""Logged meals of one user (B-21): a log row with its foods, grams and computed macros."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.repositories.library import FoodRecord
from app.repositories.sync import SyncPosition


@dataclass
class NewLogItem:
    food_item_id: int
    grams: Decimal
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


@dataclass
class LogItemRecord:
    food: FoodRecord
    grams: Decimal
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


@dataclass
class NutritionLogRecord:
    id: int
    user_id: int
    client_uuid: UUID
    log_date: date
    meal_type: str
    meal_photo_url: str | None
    actual_calories: Decimal
    actual_protein_g: Decimal
    actual_fat_g: Decimal
    actual_carbs_g: Decimal
    hunger_level_before: int | None
    hunger_level_after: int | None
    planned_meal_id: int | None
    recognition_id: int | None
    logged_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    items: list[LogItemRecord] = field(default_factory=list)


@dataclass
class DayTotals:
    logs_count: int
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal
    avg_hunger_before: float | None
    avg_hunger_after: float | None


@dataclass
class DietTargets:
    calories: int
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


class NutritionLogRepository(Protocol):
    async def changed_since(self, user_id: int, position: SyncPosition | None,
                            limit: int) -> list[NutritionLogRecord]:
        """Logs (tombstones included) after `position`, ordered by (updated_at, id); sync pull (B-27)."""
        ...

    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> NutritionLogRecord | None:
        """Including a deleted one (a tombstone keeps its client uuid)."""
        ...

    async def active_foods(self, ids: list[int]) -> dict[int, FoodRecord]: ...
    async def planned_meal_exists(self, user_id: int, meal_id: int) -> bool:
        """The meal belongs to a diet plan of that user."""
        ...

    async def create_log(self, user_id: int, values: dict, items: list[NewLogItem]) -> NutritionLogRecord: ...
    async def get_log(self, user_id: int, log_id: int) -> NutritionLogRecord | None:
        """A live log of the user; None for missing, deleted or other users' ones."""
        ...

    async def list_logs(self, user_id: int, date_from: date | None, date_to: date | None, limit: int,
                        offset: int) -> tuple[list[NutritionLogRecord], int]: ...

    async def update_log(self, user_id: int, log_id: int, values: dict,
                         items: list[NewLogItem] | None) -> NutritionLogRecord | None:
        """Update fields; `items` replaces all foods when given. None for missing or foreign logs."""
        ...

    async def soft_delete(self, user_id: int, log_id: int, at: datetime) -> bool: ...
    async def day_totals(self, user_id: int, day: date) -> DayTotals: ...

    async def logged_planned_meal_ids(self, user_id: int, day: date) -> set[int]:
        """Planned meals that a live log of that day refers to (they are eaten; no need to suggest them again)."""
        ...
    async def active_diet_targets(self, user_id: int) -> DietTargets | None: ...
