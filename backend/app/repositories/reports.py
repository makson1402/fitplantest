"""Stored progress reports of one user (B-25)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass
class ReportRecord:
    id: int
    user_id: int
    report_type: str
    period_start: date
    period_end: date
    weight_difference_kg: Decimal | None
    training_volume_kg: Decimal
    training_sessions_completed: int
    training_sessions_planned: int
    workout_compliance_pct: Decimal | None
    diet_compliance_pct: Decimal | None
    avg_daily_calories: int | None
    estimated_goal_completion_date: date | None
    irregular_data: bool
    is_auto: bool
    details: dict
    generated_at: datetime


class ReportRepository(Protocol):
    async def upsert(self, user_id: int, values: dict) -> ReportRecord:
        """Insert, or replace the figures of the report with the same (type, period): UNIQUE in the schema."""
        ...

    async def insert_if_absent(self, user_id: int, values: dict) -> ReportRecord | None:
        """Insert; None when a report of the same (type, period) already exists (it is left untouched)."""
        ...

    async def exists(self, user_id: int, report_type: str, start: date, end: date) -> bool: ...
    async def get(self, user_id: int, report_id: int) -> ReportRecord | None: ...

    async def list(self, user_id: int, report_type: str | None, limit: int,
                   offset: int) -> tuple[list[ReportRecord], int]:
        """Newest period first, then newest id; with the total number of reports that match."""
        ...
