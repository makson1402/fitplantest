"""Auth routes (B-03). Contract: docs/api/openapi.yaml, tag `auth`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import ClockDep, CurrentUser, SettingsDep, UowDep
from app.core.rate_limit import auth_rate_limit
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.common import Error
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(uow: UowDep, settings: SettingsDep, clock: ClockDep) -> AuthService:
    return AuthService(uow, settings, clock)


AuthDep = Annotated[AuthService, Depends(get_auth_service)]
RateLimited = [Depends(auth_rate_limit)]

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_409 = {409: {"model": Error, "description": "Conflict (for example email already used, plan state)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}
_429 = {429: {"model": Error, "description": "Rate limit exceeded"}}


@router.post("/register", operation_id="register", summary="Create an account with email and password",
             status_code=201, response_model=TokenPair, dependencies=RateLimited, responses={**_409, **_422, **_429})
async def register(body: RegisterRequest, service: AuthDep) -> TokenPair:
    return await service.register(body.email, body.password, body.timezone)


@router.post("/login", operation_id="login", summary="Sign in with email and password", response_model=TokenPair,
             dependencies=RateLimited, responses={**_401, **_422, **_429})
async def login(body: LoginRequest, service: AuthDep) -> TokenPair:
    return await service.login(body.email, body.password, body.device_label)


@router.post("/refresh", operation_id="refreshToken",
             summary="Exchange a refresh token for a new token pair (rotation)", response_model=TokenPair,
             responses=_401)
async def refresh(body: RefreshRequest, service: AuthDep) -> TokenPair:
    return await service.refresh(body.refresh_token)


@router.post("/logout", operation_id="logout", summary="Revoke the refresh token family", status_code=204,
             response_class=Response, responses=_401)
async def logout(body: RefreshRequest, user: CurrentUser, service: AuthDep) -> Response:
    await service.logout(user, body.refresh_token)
    return Response(status_code=204)
