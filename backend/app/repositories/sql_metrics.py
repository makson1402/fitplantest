"""SQLAlchemy implementation of `BodyMetricsRepository` (B-17)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.training import BodyMetrics
from app.repositories.metrics import BodyMetricsRecord


def _record(r: BodyMetrics) -> BodyMetricsRecord:
    return BodyMetricsRecord(
        id=r.id, user_id=r.user_id, client_uuid=r.client_uuid, measured_on=r.measured_on, weight_kg=r.weight_kg,
        chest_cm=r.chest_cm, waist_cm=r.waist_cm, thigh_cm=r.thigh_cm, bicep_cm=r.bicep_cm, hip_cm=r.hip_cm,
        calf_cm=r.calf_cm, body_fat_percent=r.body_fat_percent, created_at=r.created_at, updated_at=r.updated_at,
        deleted_at=r.deleted_at)


class SqlBodyMetricsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> BodyMetricsRecord | None:
        row = await self.session.scalar(select(BodyMetrics).where(
            BodyMetrics.user_id == user_id, BodyMetrics.client_uuid == client_uuid)
            .execution_options(populate_existing=True))
        return _record(row) if row else None

    async def find_by_day(self, user_id: int, measured_on: date) -> BodyMetricsRecord | None:
        row = await self.session.scalar(select(BodyMetrics).where(
            BodyMetrics.user_id == user_id, BodyMetrics.measured_on == measured_on, BodyMetrics.deleted_at.is_(None))
            .execution_options(populate_existing=True))
        return _record(row) if row else None

    async def insert(self, user_id: int, values: dict) -> BodyMetricsRecord:
        row = await self.session.scalar(insert(BodyMetrics).values(user_id=user_id, **values).returning(BodyMetrics),
                                        execution_options={"populate_existing": True})
        return _record(row)

    async def update(self, user_id: int, record_id: int, values: dict) -> BodyMetricsRecord | None:
        row = await self.session.scalar(
            update(BodyMetrics).where(BodyMetrics.id == record_id, BodyMetrics.user_id == user_id,
                                      BodyMetrics.deleted_at.is_(None)).values(**values).returning(BodyMetrics),
            execution_options={"populate_existing": True})
        return _record(row) if row else None

    async def list(self, user_id: int, date_from: date | None, date_to: date | None) -> list[BodyMetricsRecord]:
        conditions = [BodyMetrics.user_id == user_id, BodyMetrics.deleted_at.is_(None)]
        if date_from is not None:
            conditions.append(BodyMetrics.measured_on >= date_from)
        if date_to is not None:
            conditions.append(BodyMetrics.measured_on <= date_to)
        rows = await self.session.scalars(select(BodyMetrics).where(*conditions)
                                          .order_by(BodyMetrics.measured_on.desc(), BodyMetrics.id.desc())
                                          .execution_options(populate_existing=True))
        return [_record(r) for r in rows]

    async def soft_delete(self, user_id: int, record_id: int, at: datetime) -> bool:
        done = await self.session.scalar(
            update(BodyMetrics).where(BodyMetrics.id == record_id, BodyMetrics.user_id == user_id,
                                      BodyMetrics.deleted_at.is_(None)).values(deleted_at=at)
            .returning(BodyMetrics.id))
        return done is not None

    async def latest(self, user_id: int) -> BodyMetricsRecord | None:
        row = await self.session.scalar(select(BodyMetrics).where(
            BodyMetrics.user_id == user_id, BodyMetrics.deleted_at.is_(None))
            .order_by(BodyMetrics.measured_on.desc(), BodyMetrics.id.desc()).limit(1)
            .execution_options(populate_existing=True))
        return _record(row) if row else None
