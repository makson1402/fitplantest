"""In-memory persistence with transaction semantics: changes not committed are rolled back at the end of the request."""
from __future__ import annotations

import copy
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.repositories import EmailAlreadyExists, RefreshTokenRecord, UserRecord


class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)):
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@dataclass
class Store:
    users: dict[int, UserRecord] = field(default_factory=dict)
    tokens: dict[int, RefreshTokenRecord] = field(default_factory=dict)
    next_id: int = 1


class _Users:
    def __init__(self, uow: FakeUnitOfWork):
        self.uow = uow

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        u = self.uow.data.users.get(user_id)
        return replace(u) if u else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        return next((replace(u) for u in self.uow.data.users.values() if u.email == email), None)

    async def add(self, *, email: str, password_hash: str | None, timezone: str) -> UserRecord:
        d = self.uow.data
        if any(u.email == email for u in d.users.values()):
            raise EmailAlreadyExists(email)
        user = UserRecord(d.next_id, email, password_hash, timezone, True, self.uow.clock.now())
        d.users[user.id], d.next_id = user, d.next_id + 1
        return replace(user)


class _Tokens:
    def __init__(self, uow: FakeUnitOfWork):
        self.uow = uow

    async def add(self, *, user_id: int, family_id: UUID, token_hash: str, expires_at: datetime,
                  device_label: str | None) -> RefreshTokenRecord:
        d = self.uow.data
        rec = RefreshTokenRecord(d.next_id, user_id, family_id, token_hash, expires_at, None, device_label,
                                 self.uow.clock.now())
        d.tokens[rec.id], d.next_id = rec, d.next_id + 1
        return replace(rec)

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        return next((replace(t) for t in self.uow.data.tokens.values() if t.token_hash == token_hash), None)

    async def revoke(self, token_id: int, at: datetime) -> None:
        t = self.uow.data.tokens[token_id]
        t.revoked_at = t.revoked_at or at

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        for t in self.uow.data.tokens.values():
            if t.family_id == family_id and t.revoked_at is None:
                t.revoked_at = at


class FakeUnitOfWork:
    def __init__(self, store: Store, clock: FakeClock):
        self.store, self.clock = store, clock
        self.data = copy.deepcopy(store)
        self.users, self.refresh_tokens = _Users(self), _Tokens(self)

    async def commit(self) -> None:
        self.store.__dict__.update(copy.deepcopy(self.data).__dict__)

    async def rollback(self) -> None:
        self.data = copy.deepcopy(self.store)


def uow_factory(store: Store, clock: FakeClock):
    @asynccontextmanager
    async def factory():
        yield FakeUnitOfWork(store, clock)  # uncommitted changes live only in this instance

    return factory
