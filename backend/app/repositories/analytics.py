"""Read-only queries for analytics and the goal prediction (B-23, B-24). Everything is scoped to one user and ignores
deleted (soft-deleted) rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass
class LoggedSet:
    """A completed set with a weight, for tonnage and key lifts."""

    workout_id: int
    performed_on: date
    exercise_id: int
    exercise_name: str
    set_number: int
    reps: int
    weight_kg: Decimal


class AnalyticsRepository(Protocol):
    async def record_days(self, user_id: int, limit: int) -> set[date]:
        """Up to `limit` distinct calendar days that have any live record (workout, nutrition log, body metric)."""
        ...

    async def weighins(self, user_id: int, date_from: date, date_to: date) -> list[tuple[date, float]]: ...
    async def workout_dates(self, user_id: int, date_from: date, date_to: date) -> list[date]:
        """One entry per live workout (a date can repeat)."""
        ...

    async def completed_sets(self, user_id: int, date_from: date, date_to: date) -> list[LoggedSet]:
        """Completed sets with a weight above zero, oldest first (performed_on, workout id, set number)."""
        ...

    async def daily_calories(self, user_id: int, date_from: date, date_to: date) -> dict[date, float]:
        """Calories per day over the live nutrition logs; days without logs are absent."""
        ...
