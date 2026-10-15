from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str | None = None
    code: str
    message: str | None = None


class Error(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: Literal["up", "down"] | None = None
    mongo: Literal["up", "down"] | None = None
    ai_service: Literal["up", "down"] | None = None
