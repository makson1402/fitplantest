"""Workout logs, personal records and plan adjustments of one user (B-15, B-16)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.repositories.sync import SyncPosition
from app.repositories.training import SessionExerciseRecord


@dataclass
class SetRecord:
    exercise_id: int
    set_number: int
    reps: int
    weight_kg: Decimal
    rpe: int | None
    completed: bool
    session_exercise_id: int | None = None
    id: int = 0


@dataclass
class WorkoutRecord:
    id: int
    user_id: int
    client_uuid: UUID
    training_session_id: int | None
    performed_on: date
    started_at: datetime | None
    finished_at: datetime | None
    overall_rpe: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    sets: list[SetRecord] = field(default_factory=list)


@dataclass
class AdjustmentRecord:
    session_exercise_id: int
    exercise_id: int
    exercise_name: str
    reason: str
    old_sets: int | None
    new_sets: int | None
    old_reps: int | None
    new_reps: int | None
    old_weight_kg: Decimal | None
    new_weight_kg: Decimal | None


@dataclass
class PersonalRecordRecord:
    exercise_id: int
    exercise_name: str
    max_weight_kg: Decimal
    max_reps: int
    estimated_1rm_kg: Decimal
    achieved_on: date


@dataclass
class PlannedForAdaptation:
    planned: SessionExerciseRecord
    is_bodyweight: bool
    body_region: str  # upper | lower | core (decides the progression step)


@dataclass
class SessionForAdaptation:
    session_id: int
    plan_status: str
    exercises: list[PlannedForAdaptation]


class WorkoutRepository(Protocol):
    async def changed_since(self, user_id: int, position: SyncPosition | None, limit: int) -> list[WorkoutRecord]:
        """Workouts (tombstones included) after `position`, ordered by (updated_at, id); sync pull (B-27)."""
        ...

    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> WorkoutRecord | None:
        """Including a deleted one (a tombstone keeps its client uuid)."""
        ...

    async def existing_exercise_ids(self, ids: list[int]) -> set[int]: ...

    async def session_for_adaptation(self, user_id: int, session_id: int) -> SessionForAdaptation | None:
        """None when the session does not exist or its plan belongs to another user."""
        ...

    async def create_workout(self, user_id: int, values: dict, sets: list[SetRecord]) -> WorkoutRecord: ...
    async def get_workout(self, user_id: int, workout_id: int) -> WorkoutRecord | None:
        """A live workout of the user; None for missing, deleted or other users' ones."""
        ...

    async def list_workouts(self, user_id: int, date_from: date | None, date_to: date | None, limit: int,
                            offset: int) -> tuple[list[WorkoutRecord], int]: ...

    async def replace_workout(self, user_id: int, workout_id: int, values: dict,
                              sets: list[SetRecord]) -> WorkoutRecord | None: ...

    async def soft_delete(self, user_id: int, workout_id: int, at: datetime) -> bool: ...
    async def has_workout(self, user_id: int, session_id: int, performed_on: date) -> bool: ...

    async def add_adjustment(self, session_exercise_id: int, workout_id: int, reason: str,
                             old: tuple[int, int, Decimal | None], new: tuple[int, int, Decimal | None]) -> None: ...

    async def adjustments_of(self, workout_id: int) -> list[AdjustmentRecord]: ...

    async def current_e1rm(self, user_id: int, exercise_id: int) -> float | None: ...
    async def replace_record(self, user_id: int, exercise_id: int, *, weight: Decimal, reps: int, e1rm: Decimal,
                             achieved_on: date, source_set_id: int | None) -> None:
        """Retire the current record of the exercise and insert the new one."""
        ...

    async def records_of(self, workout_id: int) -> list[PersonalRecordRecord]:
        """Records whose source set belongs to the workout."""
        ...

    async def current_records(self, user_id: int) -> list[PersonalRecordRecord]: ...
