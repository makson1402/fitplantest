"""Auth request/response models, mirroring `components.schemas` of docs/api/openapi.yaml."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import password_too_long
from app.core.timezones import is_valid_timezone

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
    timezone: str = Field(default=None, description="IANA name", examples=["Europe/Warsaw"])  # type: ignore[assignment]

    _password = field_validator("password")(check_new_password)

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str) -> str:
        if not is_valid_timezone(value):
            raise ValueError("Unknown IANA time zone")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_label: str = None  # type: ignore[assignment]  # optional, never null


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)  # token_type is always sent

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - not a secret
    expires_in: int = Field(description="Access token lifetime in seconds")
