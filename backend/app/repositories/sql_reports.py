"""SQLAlchemy implementation of `ReportRepository` (B-25)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reports import ProgressReport
from app.repositories.reports import ReportRecord

_FIELDS = ("id", "user_id", "report_type", "period_start", "period_end", "weight_difference_kg", "training_volume_kg",
           "training_sessions_completed", "training_sessions_planned", "workout_compliance_pct", "diet_compliance_pct",
           "avg_daily_calories", "estimated_goal_completion_date", "irregular_data", "is_auto", "details",
           "generated_at")


def _record(row: ProgressReport) -> ReportRecord:
    return ReportRecord(**{name: getattr(row, name) for name in _FIELDS})


class SqlReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, user_id: int, values: dict) -> ReportRecord:
        stmt = insert(ProgressReport).values(user_id=user_id, **values)
        refreshed = {k: v for k, v in values.items() if k not in ("report_type", "period_start", "period_end")}
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "report_type", "period_start", "period_end"],
            set_={**refreshed, "generated_at": func.now()}).returning(ProgressReport)
        row = await self.session.scalar(stmt, execution_options={"populate_existing": True})
        return _record(row)

    async def get(self, user_id: int, report_id: int) -> ReportRecord | None:
        row = await self.session.scalar(select(ProgressReport).where(
            ProgressReport.id == report_id, ProgressReport.user_id == user_id)
            .execution_options(populate_existing=True))
        return _record(row) if row else None

    async def list(self, user_id: int, report_type: str | None, limit: int,
                   offset: int) -> tuple[list[ReportRecord], int]:
        conditions = [ProgressReport.user_id == user_id]
        if report_type is not None:
            conditions.append(ProgressReport.report_type == report_type)
        total = await self.session.scalar(select(func.count()).select_from(ProgressReport).where(*conditions))
        rows = await self.session.scalars(
            select(ProgressReport).where(*conditions)
            .order_by(ProgressReport.period_start.desc(), ProgressReport.id.desc()).limit(limit).offset(offset)
            .execution_options(populate_existing=True))
        return [_record(r) for r in rows], int(total or 0)
