"""Workout schemas (docs/api/openapi.yaml: WorkoutInput, Workout, WorkoutResult, PlanAdjustment, ...)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.ids import Id32, Id64
from app.schemas.training import TrainingSession

AdjustmentReason = Literal["baseline", "reduce_high_rpe", "reduce_incomplete_set", "progression"]


class WorkoutSetInput(BaseModel):
    exercise_id: Id32
    session_exercise_id: Id64 | None = None
    set_number: int = Field(ge=1)
    reps: int = Field(ge=0, le=200)
    weight_kg: float = Field(default=0, ge=0, allow_inf_nan=False)  # the 9999.99 column limit: services/workouts.py
    rpe: int | None = Field(default=None, ge=1, le=10)
    completed: bool = Field(default=True, description="False when the set could not be completed (a reduce signal)")


class WorkoutInput(BaseModel):
    # Optional; the defaults are never validated: an absent field is None, an explicit `null` is a 422.
    client_uuid: UUID = Field(default=None, description="Set by the app; makes retries and sync idempotent")  # type: ignore[assignment]
    training_session_id: Id64 | None = None
    performed_on: date
    started_at: datetime | None = None
    finished_at: datetime | None = None
    overall_rpe: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None, max_length=1000)
    sets: list[WorkoutSetInput] = Field(min_length=1)


class Workout(WorkoutInput):
    id: int
    client_uuid: UUID
    created_at: datetime
    updated_at: datetime


class WorkoutPage(BaseModel):
    items: list[Workout]
    total: int
    limit: int
    offset: int


class PlanAdjustment(BaseModel):
    session_exercise_id: int
    exercise_id: int
    exercise_name: str = ""
    reason: AdjustmentReason
    old_sets: int | None = None
    new_sets: int | None = None
    old_reps: int | None = None
    new_reps: int | None = None
    old_weight_kg: float | None = None
    new_weight_kg: float | None = None


class PersonalRecord(BaseModel):
    exercise_id: int
    exercise_name: str
    max_weight_kg: float
    max_reps: int
    estimated_1rm_kg: float
    achieved_on: date


class WorkoutResult(BaseModel):
    workout: Workout
    adjustments: list[PlanAdjustment] = Field(description="Empty when there was no explicit signal")
    new_personal_records: list[PersonalRecord]


class NextSession(BaseModel):
    session: TrainingSession
    scheduled_date: date
