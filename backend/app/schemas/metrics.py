"""Body measurement schemas (docs/api/openapi.yaml: BodyMetricsInput, BodyMetrics)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

_FINITE = {"allow_inf_nan": False}


class BodyMetricsInput(BaseModel):
    # Optional; the default is never validated: an absent field is None, an explicit `null` is a 422.
    client_uuid: UUID = Field(default=None)  # type: ignore[assignment]
    measured_on: date
    weight_kg: float = Field(ge=30, le=300, **_FINITE)
    chest_cm: float | None = Field(default=None, gt=0, **_FINITE)
    waist_cm: float | None = Field(default=None, gt=0, **_FINITE)
    thigh_cm: float | None = Field(default=None, gt=0, **_FINITE)
    bicep_cm: float | None = Field(default=None, gt=0, **_FINITE)
    hip_cm: float | None = Field(default=None, gt=0, **_FINITE)
    calf_cm: float | None = Field(default=None, gt=0, **_FINITE)
    body_fat_percent: float | None = Field(default=None, ge=2, le=70, **_FINITE)


class BodyMetrics(BodyMetricsInput):
    id: int
    client_uuid: UUID
    updated_at: datetime
