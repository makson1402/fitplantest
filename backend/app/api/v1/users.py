"""Account routes (B-05). Contract: docs/api/openapi.yaml, tag `account`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import ClockDep, CurrentUser, SettingsDep, UowDep
from app.core.rate_limit import auth_rate_limit
from app.schemas import account as s
from app.schemas.common import Error
from app.services.account import AccountService

router = APIRouter(prefix="/users/me", tags=["account"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_409 = {409: {"model": Error, "description": "Conflict (for example email already used)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}
_429 = {429: {"model": Error, "description": "Rate limit exceeded"}}
Limited = [Depends(auth_rate_limit)]  # these routes check a password: slow down guessing


def get_service(request: Request, uow: UowDep, settings: SettingsDep, clock: ClockDep) -> AccountService:
    return AccountService(uow, settings, clock, request.app.state.mongo_db)


Service = Annotated[AccountService, Depends(get_service)]


@router.get("", operation_id="getMe", summary="Current user", response_model=s.User, responses=_401)
async def get_me(user: CurrentUser, service: Service) -> s.User:
    return await service.me(user)


@router.patch("", operation_id="updateMe", summary="Update name, surname or time zone", response_model=s.User,
              responses={**_401, **_422})
async def update_me(body: s.UserUpdate, user: CurrentUser, service: Service) -> s.User:
    return await service.update_me(user, body)


@router.post("/email", operation_id="changeEmail", summary="Change the email (current password required)",
             response_model=s.User, dependencies=Limited, responses={**_401, **_409, **_422, **_429})
async def change_email(body: s.ChangeEmailRequest, user: CurrentUser, service: Service) -> s.User:
    return await service.change_email(user, body)


@router.post("/password", operation_id="changePassword", summary="Change the password (current password required)",
             status_code=204, response_class=Response, dependencies=Limited, responses={**_401, **_422, **_429})
async def change_password(body: s.ChangePasswordRequest, user: CurrentUser, service: Service) -> Response:
    await service.change_password(user, body)
    return Response(status_code=204)


@router.post("/delete", operation_id="deleteAccount", summary="Delete the account with all related data",
             description="Removes rows in PostgreSQL, documents in MongoDB and photo files. Not reversible.",
             status_code=204, response_class=Response, dependencies=Limited, responses={**_401, **_422, **_429})
async def delete_account(body: s.DeleteAccountRequest, user: CurrentUser, service: Service) -> Response:
    await service.delete(user, body)
    return Response(status_code=204)
