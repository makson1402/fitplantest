"""SQLAlchemy (async) implementation of the repository interfaces in `app.repositories`.

One `SqlUnitOfWork` wraps one `AsyncSession` = one database transaction per request. Nothing is persisted
until `commit()`; leaving the context manager rolls back whatever was not committed.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models.account import RefreshToken, User
from app.repositories import (
    EmailAlreadyExists,
    RefreshTokenRecord,
    UnitOfWork,
    UnitOfWorkFactory,
    UserRecord,
)
from app.repositories.sql_analytics import SqlAnalyticsRepository
from app.repositories.sql_diet import SqlDietRepository
from app.repositories.sql_library import SqlLibraryRepository
from app.repositories.sql_metrics import SqlBodyMetricsRepository
from app.repositories.sql_nutrition_log import SqlNutritionLogRepository
from app.repositories.sql_profile import SqlProfileRepository
from app.repositories.sql_training import SqlTrainingRepository
from app.repositories.sql_workouts import SqlWorkoutRepository


def _user(row: User) -> UserRecord:
    return UserRecord(row.id, row.email, row.password_hash, row.timezone, row.is_active, row.created_at)


def _token(row: RefreshToken) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        row.id, row.user_id, row.family_id, row.token_hash, row.expires_at, row.revoked_at, row.device_label,
        row.created_at,
    )


class SqlUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        row = await self.session.get(User, user_id)
        return _user(row) if row else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self.session.scalar(select(User).where(User.email == email))
        return _user(row) if row else None

    async def add(self, *, email: str, password_hash: str | None, timezone: str) -> UserRecord:
        stmt = insert(User).values(email=email, password_hash=password_hash, timezone=timezone).returning(User)
        try:
            row = await self.session.scalar(stmt, execution_options={"populate_existing": True})
        except IntegrityError as exc:
            # users_email_key is the only unique constraint a registration can hit.
            if "users_email_key" in str(exc.orig):
                raise EmailAlreadyExists(email) from exc
            raise
        return _user(row)


class SqlRefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, *, user_id: int, family_id: UUID, token_hash: str, expires_at: datetime,
                  device_label: str | None) -> RefreshTokenRecord:
        stmt = insert(RefreshToken).values(
            user_id=user_id, family_id=family_id, token_hash=token_hash, expires_at=expires_at,
            device_label=device_label,
        ).returning(RefreshToken)
        return _token(await self.session.scalar(stmt, execution_options={"populate_existing": True}))

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        stmt = (select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
                .execution_options(populate_existing=True))
        row = await self.session.scalar(stmt)
        return _token(row) if row else None

    async def revoke(self, token_id: int, at: datetime) -> None:
        await self.session.execute(
            update(RefreshToken).where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )


class SqlUnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = SqlUserRepository(session)
        self.refresh_tokens = SqlRefreshTokenRepository(session)
        self.library = SqlLibraryRepository(session)
        self.profile = SqlProfileRepository(session)
        self.training = SqlTrainingRepository(session)
        self.diet = SqlDietRepository(session)
        self.workouts = SqlWorkoutRepository(session)
        self.metrics = SqlBodyMetricsRepository(session)
        self.nutrition_log = SqlNutritionLogRepository(session)
        self.analytics = SqlAnalyticsRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def sql_uow_factory(engine: AsyncEngine) -> UnitOfWorkFactory:
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def factory() -> AsyncIterator[UnitOfWork]:
        async with sessions() as session:  # closing the session rolls back anything uncommitted
            yield SqlUnitOfWork(session)

    return factory


async def postgres_probe(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:  # noqa: BLE001  (any failure means "down")
        return False
    return True
