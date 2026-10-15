"""Auth request/response models, mirroring `components.schemas` of docs/api/openapi.yaml."""
from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import password_too_long

Email = Annotated[EmailStr, Field(max_length=254)]


def check_new_password(value: str) -> str:
    """Contract: 8-72 characters, at least one letter and one digit, at most 72 bytes (bcrypt)."""
    if password_too_long(value):
        raise ValueError("Password must be at most 72 bytes")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=72,
                          description="At least one letter and one digit; at most 72 bytes (bcrypt)")
    timezone: str | None = Field(default=None, description="IANA name", examples=["Europe/Warsaw"])

    _password = field_validator("password")(check_new_password)

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA time zone") from exc
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_label: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - not a secret
    expires_in: int = Field(description="Access token lifetime in seconds")
