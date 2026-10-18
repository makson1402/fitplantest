"""Report schemas (docs/api/openapi.yaml: Report, ReportPage, CreateReportRequest)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ReportType = Literal["weekly", "monthly", "custom"]


class CreateReportRequest(BaseModel):
    period_start: date
    period_end: date

    @field_validator("period_end")
    @classmethod
    def _not_before_start(cls, value: date, info) -> date:
        start = info.data.get("period_start")
        if start is not None and value < start:
            raise ValueError("period_end must not be before period_start")
        return value


class Report(BaseModel):
    id: int
    report_type: ReportType
    period_start: date
    period_end: date
    weight_difference_kg: float | None = None
    training_volume_kg: float
    training_sessions_completed: int
    training_sessions_planned: int
    workout_compliance_pct: float | None = None
    diet_compliance_pct: float | None = None
    avg_daily_calories: int | None = None
    estimated_goal_completion_date: date | None = None
    irregular_data: bool
    is_auto: bool
    details: dict[str, Any] = Field(default_factory=dict, description="Chart series and key lifts")
    generated_at: datetime


class ReportPage(BaseModel):
    items: list[Report]
    total: int
    limit: int
    offset: int
