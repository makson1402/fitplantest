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


class RefreshTokenRepository(Protocol):
    async def add(self, *, user_id: int, family_id: UUID, token_hash: str, expires_at: datetime,
                  device_label: str | None) -> RefreshTokenRecord: ...

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        """Lock the row (SELECT ... FOR UPDATE) so two concurrent refreshes cannot both rotate it."""
        ...

    async def revoke(self, token_id: int, at: datetime) -> None: ...
    async def revoke_family(self, family_id: UUID, at: datetime) -> None: ...


class UnitOfWork(Protocol):
    users: UserRepository
    refresh_tokens: RefreshTokenRepository

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


# Called once per request; the context manager rolls back anything not committed.
UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[UnitOfWork]]
UnitOfWorkIterator = AsyncIterator[UnitOfWork]
