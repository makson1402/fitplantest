"""Offline sync schemas (docs/api/openapi.yaml: SyncPushRequest/Response, SyncPullResponse). Design: D-07."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Error
from app.schemas.metrics import BodyMetrics, BodyMetricsInput
from app.schemas.nutrition_log import NutritionLog, NutritionLogInput
from app.schemas.workouts import Workout, WorkoutInput


class SyncWorkout(WorkoutInput):
    client_uuid: UUID
    base_updated_at: datetime | None = Field(
        default=None, description="The server updated_at the client last saw; null for a new item")
    deleted: bool = Field(default=False, description="True to delete the item")


class SyncNutritionLog(NutritionLogInput):
    client_uuid: UUID
    base_updated_at: datetime | None = Field(
        default=None, description="The server updated_at the client last saw; null for a new item")
    deleted: bool = Field(default=False, description="True to delete the item")


class SyncBodyMetrics(BodyMetricsInput):
    client_uuid: UUID
    base_updated_at: datetime | None = Field(
        default=None, description="The server updated_at the client last saw; null for a new item")
    deleted: bool = Field(default=False, description="True to delete the item")


class SyncPushRequest(BaseModel):
    workouts: list[SyncWorkout] = Field(default=None)  # type: ignore[assignment]
    nutrition_logs: list[SyncNutritionLog] = Field(default=None)  # type: ignore[assignment]
    body_metrics: list[SyncBodyMetrics] = Field(default=None)  # type: ignore[assignment]


class SyncItemResult(BaseModel):
    type: Literal["workout", "nutrition_log", "body_metrics"]
    client_uuid: UUID
    status: Literal["applied", "unchanged", "conflict", "rejected"]
    server_id: int | None = None
    server_updated_at: datetime | None = None
    error: Error | None = None
    server_copy: dict[str, Any] | None = Field(default=None, description="The stored item, present on conflict")


class SyncPushResponse(BaseModel):
    results: list[SyncItemResult]
    cursor: str


class SyncWorkoutOut(Workout):
    deleted_at: datetime | None = None


class SyncNutritionLogOut(NutritionLog):
    deleted_at: datetime | None = None


class SyncBodyMetricsOut(BodyMetrics):
    deleted_at: datetime | None = None


class SyncPullResponse(BaseModel):
    cursor: str
    has_more: bool
    workouts: list[SyncWorkoutOut]
    nutrition_logs: list[SyncNutritionLogOut]
    body_metrics: list[SyncBodyMetricsOut]
