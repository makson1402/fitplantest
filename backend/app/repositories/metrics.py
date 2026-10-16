"""Body measurements of one user (B-17): history with one live measurement per day."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass
class BodyMetricsRecord:
    id: int
    user_id: int
    client_uuid: UUID
    measured_on: date
    weight_kg: Decimal
    chest_cm: Decimal | None
    waist_cm: Decimal | None
    thigh_cm: Decimal | None
    bicep_cm: Decimal | None
    hip_cm: Decimal | None
    calf_cm: Decimal | None
    body_fat_percent: Decimal | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class BodyMetricsRepository(Protocol):
    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> BodyMetricsRecord | None:
        """Including a deleted one (a tombstone keeps its client uuid)."""
        ...

    async def find_by_day(self, user_id: int, measured_on: date) -> BodyMetricsRecord | None:
        """The live (not deleted) measurement of that day."""
        ...

    async def insert(self, user_id: int, values: dict) -> BodyMetricsRecord: ...
    async def update(self, user_id: int, record_id: int, values: dict) -> BodyMetricsRecord | None: ...
    async def list(self, user_id: int, date_from: date | None, date_to: date | None) -> list[BodyMetricsRecord]: ...
    async def soft_delete(self, user_id: int, record_id: int, at: datetime) -> bool: ...

    async def latest(self, user_id: int) -> BodyMetricsRecord | None:
        """The live measurement with the latest `measured_on`."""
        ...
