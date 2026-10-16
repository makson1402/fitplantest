"""Training plans of one user (B-11): plan, sessions and planned exercises, with the plan lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.repositories.library import ExerciseRecord


@dataclass
class NewSessionExercise:
    exercise_id: int
    position: int
    sets: int
    reps: int
    rest_seconds: int


@dataclass
class NewSession:
    session_order: int
    name: str
    weekday: str
    estimated_duration_min: int
    exercises: list[NewSessionExercise]


@dataclass
class SessionExerciseRecord:
    id: int
    position: int
    exercise: ExerciseRecord
    original_exercise_id: int | None
    planned_sets: int
    planned_reps: int
    planned_weight_kg: Decimal | None
    rest_seconds: int


@dataclass
class SessionRecord:
    id: int
    session_order: int
    name: str
    weekday: str
    estimated_duration_min: int
    exercises: list[SessionExerciseRecord] = field(default_factory=list)


@dataclass
class PlanRecord:
    id: int
    user_id: int
    name: str
    goal: str
    num_training_days: int
    experience_level: str
    equipment: str
    status: str
    skipped_groups: list[tuple[int, str]]  # (muscle group id, name)
    generated_at: datetime
    start_date: date | None
    end_date: date | None
    sessions: list[SessionRecord] = field(default_factory=list)


@dataclass
class SessionExerciseContext:
    """A planned exercise with what its plan and session say about it (for editing and swapping)."""

    record: SessionExerciseRecord
    plan_id: int
    plan_status: str
    plan_experience_level: str
    plan_equipment: str
    session_id: int
    session_exercise_ids: list[int]  # exercise ids currently in the same session (including this one)


class TrainingRepository(Protocol):
    async def lock_user(self, user_id: int) -> None:
        """Serialise the plan operations of one user (generate, accept) for the rest of the transaction."""
        ...

    async def delete_draft(self, user_id: int) -> None: ...

    async def create_plan(self, user_id: int, *, name: str, goal: str, num_training_days: int,
                          experience_level: str, equipment: str, skipped_group_ids: list[int],
                          sessions: list[NewSession]) -> int:
        """Insert a draft plan with its sessions and exercises; returns the plan id."""
        ...

    async def get_plan(self, user_id: int, plan_id: int) -> PlanRecord | None:
        """None when it does not exist or belongs to another user."""
        ...

    async def get_plan_by_status(self, user_id: int, status: str) -> PlanRecord | None: ...

    async def get_session_exercise(self, user_id: int, session_exercise_id: int) -> SessionExerciseContext | None:
        """None when it does not exist or its plan belongs to another user."""
        ...

    async def update_session_exercise(self, session_exercise_id: int, changes: dict) -> None:
        """`changes` uses the column names of `session_exercise`."""
        ...

    async def archive_active(self, user_id: int) -> None: ...
    async def activate(self, user_id: int, plan_id: int, start_date: date, end_date: date) -> None: ...
