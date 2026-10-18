"""Persistence interfaces used by the services.

The SQLAlchemy implementation is added on top of DATA's models after DB-01 is merged; until then the
tests use the in-memory implementation in `tests/fakes.py`. Records mirror `docs/database/schema_postgres.sql`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.repositories.analytics import AnalyticsRepository
from app.repositories.diet import DietRepository
from app.repositories.library import LibraryRepository
from app.repositories.metrics import BodyMetricsRepository
from app.repositories.nutrition_log import NutritionLogRepository
from app.repositories.profile import ProfileRepository
from app.repositories.reports import ReportRepository
from app.repositories.training import TrainingRepository
from app.repositories.workouts import WorkoutRepository


class EmailAlreadyExists(Exception):
    """Raised by `UserRepository.add` when the unique index on users.email is violated."""


@dataclass
class UserRecord:
    id: int
    email: str
    password_hash: str | None
    timezone: str
    is_active: bool
    created_at: datetime
    name: str | None = None
    surname: str | None = None


@dataclass
class RefreshTokenRecord:
    id: int
    user_id: int
    family_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    device_label: str | None
    created_at: datetime


class UserRepository(Protocol):
    async def get_by_id(self, user_id: int) -> UserRecord | None: ...
    async def get_by_email(self, email: str) -> UserRecord | None: ...
    async def add(self, *, email: str, password_hash: str | None, timezone: str) -> UserRecord: ...

    async def update_fields(self, user_id: int, values: dict) -> UserRecord:
        """Update name, surname or timezone (the keys are column names)."""
        ...

    async def set_email(self, user_id: int, email: str) -> UserRecord:
        """Raises `EmailAlreadyExists` when another account has that email."""
        ...

    async def set_password_hash(self, user_id: int, password_hash: str) -> None: ...

    async def delete(self, user_id: int) -> None:
        """Delete the user; every table that references it cascades (FR-U5)."""
        ...


class RefreshTokenRepository(Protocol):
    async def add(self, *, user_id: int, family_id: UUID, token_hash: str, expires_at: datetime,
                  device_label: str | None) -> RefreshTokenRecord: ...

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        """Lock the row (SELECT ... FOR UPDATE) so two concurrent refreshes cannot both rotate it."""
        ...

    async def revoke(self, token_id: int, at: datetime) -> None: ...
    async def revoke_family(self, family_id: UUID, at: datetime) -> None: ...
    async def revoke_all_for_user(self, user_id: int, at: datetime) -> None: ...


class UnitOfWork(Protocol):
    users: UserRepository
    refresh_tokens: RefreshTokenRepository
    library: LibraryRepository
    profile: ProfileRepository
    training: TrainingRepository
    diet: DietRepository
    workouts: WorkoutRepository
    metrics: BodyMetricsRepository
    nutrition_log: NutritionLogRepository
    analytics: AnalyticsRepository
    reports: ReportRepository

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


# Called once per request; the context manager rolls back anything not committed.
UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[UnitOfWork]]
UnitOfWorkIterator = AsyncIterator[UnitOfWork]
