"""Analytics schemas (docs/api/openapi.yaml: AnalyticsSummary, ChartSeries, GoalPrediction)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["week", "month", "3months"]
Metric = Literal["weight", "tonnage", "workouts_per_week", "calories", "workout_compliance", "diet_compliance"]
DataStatus = Literal["ok", "insufficient_data"]
PredictionStatus = Literal["ok", "no_target", "insufficient_data", "goal_reached", "no_progress", "moving_away"]
Warning = Literal["low_fit", "gaps", "low_training_compliance"]


class KeyLift(BaseModel):
    exercise_id: int
    exercise_name: str
    first_e1rm_kg: float
    best_e1rm_kg: float


class AnalyticsSummary(BaseModel):
    period: Period
    status: DataStatus
    from_: date = Field(alias="from", serialization_alias="from")
    to: date
    weight_change_kg: float | None = None
    total_workouts: int | None = None
    avg_workouts_per_week: float | None = None
    avg_calories: float | None = None
    tonnage_kg: float | None = None
    workout_compliance_pct: float | None = None
    diet_compliance_pct: float | None = None
    key_lifts: list[KeyLift] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ChartPoint(BaseModel):
    date: date
    value: float


class ChartSeries(BaseModel):
    metric: str
    period: str
    status: DataStatus
    points: list[ChartPoint]


class GoalPrediction(BaseModel):
    status: PredictionStatus
    estimated_date: date | None = None
    slope_kg_per_week: float | None = None
    r2: float | None = None
    target_weight_kg: float | None = None
    warnings: list[Warning]
