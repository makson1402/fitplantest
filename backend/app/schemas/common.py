from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Optional, never null (the defaults are only for the documentation: the error handler leaves absent keys out).
    field: str = None  # type: ignore[assignment]
    code: str
    message: str = None  # type: ignore[assignment]


class Error(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = None  # type: ignore[assignment]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    # A dependency that is not configured is left out of the answer (never null).
    postgres: Literal["up", "down"] = None  # type: ignore[assignment]
    mongo: Literal["up", "down"] = None  # type: ignore[assignment]
    ai_service: Literal["up", "down"] = None  # type: ignore[assignment]
