"""Biometric profile, injuries, allergens and excluded foods of one user (B-06). Every call is scoped to a user id."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.repositories.library import FoodRecord, NamedRecord


@dataclass
class ProfileRecord:
    user_id: int
    age: int
    sex: str
    weight_kg: Decimal
    height_cm: int
    activity_level_pal: Decimal
    goal: str
    target_weight_kg: Decimal | None
    experience_level: str
    equipment: str
    tdee_kcal: int | None
    updated_at: datetime


@dataclass
class InjuryRecord:
    id: int
    user_id: int
    injury_type_id: int
    injury_type_name: str
    affected_muscle_group_id: int
    affected_muscle_group_name: str
    severity: str
    start_date: date
    is_active: bool
    notes: str | None


class ProfileRepository(Protocol):
    async def get_profile(self, user_id: int) -> ProfileRecord | None: ...

    async def upsert_profile(self, user_id: int, values: dict) -> ProfileRecord:
        """Create or replace the profile (`values` use the column names of `user_profile`)."""
        ...

    async def list_injuries(self, user_id: int) -> list[InjuryRecord]: ...
    async def get_injury(self, user_id: int, injury_id: int) -> InjuryRecord | None: ...
    async def create_injury(self, user_id: int, values: dict) -> InjuryRecord: ...

    async def update_injury(self, user_id: int, injury_id: int, changes: dict) -> InjuryRecord | None:
        """None when the injury does not exist or belongs to another user."""
        ...

    async def delete_injury(self, user_id: int, injury_id: int) -> bool: ...
    async def injury_type_exists(self, injury_type_id: int) -> bool: ...
    async def muscle_group_exists(self, muscle_group_id: int) -> bool: ...

    async def user_allergens(self, user_id: int) -> list[NamedRecord]: ...
    async def existing_allergen_ids(self, ids: list[int]) -> set[int]: ...
    async def replace_user_allergens(self, user_id: int, ids: list[int]) -> None: ...

    async def excluded_foods(self, user_id: int) -> list[FoodRecord]: ...
    async def existing_food_ids(self, ids: list[int]) -> set[int]:
        """Ids of active foods among `ids`."""
        ...

    async def replace_excluded_foods(self, user_id: int, ids: list[int]) -> None: ...
