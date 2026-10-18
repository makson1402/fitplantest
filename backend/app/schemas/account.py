"""Account schemas (docs/api/openapi.yaml: User, UserUpdate, ChangeEmailRequest, ChangePasswordRequest, ...)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.timezones import is_valid_timezone
from app.schemas.auth import check_new_password


class User(BaseModel):
    id: int
    email: str = Field(json_schema_extra={"format": "email"})
    name: str | None = None
    surname: str | None = None
    timezone: str
    has_profile: bool = Field(description="False until onboarding is finished")
    created_at: datetime


class UserUpdate(BaseModel):
    """PATCH body. Only the fields the client sent change; `name` and `surname` may be cleared with `null`, the time
    zone may not (the default is never used or validated)."""

    name: str | None = Field(default=None, max_length=100)
    surname: str | None = Field(default=None, max_length=100)
    timezone: str = None  # type: ignore[assignment]

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str) -> str:
        if not is_valid_timezone(value):
            raise ValueError("Unknown IANA time zone")
        return value


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr  # the validator itself limits the length to 254
    current_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)

    _new = field_validator("new_password")(check_new_password)


class DeleteAccountRequest(BaseModel):
    confirmation: Literal["DELETE"]
    current_password: str | None = Field(default=None, description="Required for accounts that have a password")
