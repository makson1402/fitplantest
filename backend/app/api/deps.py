"""Shared FastAPI dependencies: settings, clock, unit of work, current user, object-level authorization."""
from __future__ import annotations

from typing import Annotated, Protocol

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import not_found, unauthorized
from app.core.security import decode_access_token
from app.repositories import UnitOfWork, UnitOfWorkIterator, UserRecord


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


async def get_uow(request: Request) -> UnitOfWorkIterator:
    factory = request.app.state.uow_factory
    if factory is None:
        raise RuntimeError("persistence is not configured (SQLAlchemy unit of work arrives with DB-01)")
    async with factory() as uow:
        yield uow


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]
UowDep = Annotated[UnitOfWork, Depends(get_uow)]

_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


async def get_current_user(uow: UowDep, settings: SettingsDep, clock: ClockDep,
                           creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> UserRecord:
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized()
    claims = decode_access_token(creds.credentials, clock.now(), settings.jwt_secret, settings.jwt_algorithm)
    user = await uow.users.get_by_id(claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]


class Owned(Protocol):
    user_id: int


def owned_or_404[T: Owned](row: T | None, user: UserRecord) -> T:
    """Object-level authorization: another user's row is indistinguishable from a missing one (404, never 403)."""
    if row is None or row.user_id != user.id:
        raise not_found()
    return row
