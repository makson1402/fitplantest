"""Training plan schemas (docs/api/openapi.yaml: GenerateTrainingPlanRequest, TrainingPlan, TrainingSession, ...)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ids import Id32
from app.schemas.library import Equipment, ExerciseSummary, ExperienceLevel, MuscleGroupRef
from app.schemas.profile import Goal

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PlanStatus = Literal["draft", "active", "archived"]


class GenerateTrainingPlanRequest(BaseModel):
    goal: Goal
    training_days: int = Field(ge=1, le=7)
    # Optional, defaults to the profile. The defaults are never validated: an absent field is None, an explicit
    # `null` is a 422 because the contract's type is not nullable.
    experience_level: ExperienceLevel = None  # type: ignore[assignment]
    equipment: Equipment = None  # type: ignore[assignment]


class AcceptPlanRequest(BaseModel):
    start_date: date = Field(default=None, description="Defaults to today in the user's time zone")  # type: ignore[assignment]


class SessionExercise(BaseModel):
    id: int
    position: int
    exercise: ExerciseSummary
    original_exercise_id: int | None = None
    planned_sets: int = Field(ge=1, le=10)
    planned_reps: int = Field(ge=1, le=50)
    planned_weight_kg: float | None = Field(description="Null until the first logged workout")
    rest_seconds: int = Field(ge=0, le=600)


class SessionExerciseUpdate(BaseModel):
    """PATCH body (contract: at least one property). Only the fields the client sent are applied; the defaults are
    never used or validated, so an explicit `null` is a 422 except for `planned_weight_kg`, which may be cleared."""

    model_config = ConfigDict(json_schema_extra={"minProperties": 1})

    planned_sets: int = Field(default=None, ge=1, le=10)  # type: ignore[assignment]
    planned_reps: int = Field(default=None, ge=1, le=50)  # type: ignore[assignment]
    planned_weight_kg: float | None = Field(default=None, ge=0, allow_inf_nan=False)  # 9999.99: services/training.py
    rest_seconds: int = Field(default=None, ge=0, le=600)  # type: ignore[assignment]

    @model_validator(mode="after")
    def at_least_one_field(self) -> SessionExerciseUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class SwapRequest(BaseModel):
    exercise_id: Id32


class TrainingSession(BaseModel):
    id: int
    session_order: int
    name: str
    weekday: Weekday
    estimated_duration_min: int
    exercises: list[SessionExercise]


class SkippedGroup(BaseModel):
    muscle_group: MuscleGroupRef
    reason: Literal["injury"]


class TrainingPlan(BaseModel):
    id: int
    name: str
    goal: Goal
    num_training_days: int
    experience_level: ExperienceLevel
    equipment: Equipment
    status: PlanStatus
    skipped_groups: list[SkippedGroup]
    generated_at: datetime
    start_date: date | None = None
    end_date: date | None = None
    sessions: list[TrainingSession]
