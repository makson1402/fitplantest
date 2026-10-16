"""SQLAlchemy implementation of `AnalyticsRepository` (B-23, B-24)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition import NutritionLog
from app.db.models.reference import Exercise
from app.db.models.training import BodyMetrics, WorkoutLog, WorkoutSetLog
from app.repositories.analytics import LoggedSet


class SqlAnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_days(self, user_id: int, limit: int) -> set[date]:
        days = union(
            select(WorkoutLog.performed_on.label("day")).where(WorkoutLog.user_id == user_id,
                                                               WorkoutLog.deleted_at.is_(None)),
            select(NutritionLog.log_date).where(NutritionLog.user_id == user_id, NutritionLog.deleted_at.is_(None)),
            select(BodyMetrics.measured_on).where(BodyMetrics.user_id == user_id, BodyMetrics.deleted_at.is_(None)),
        ).subquery()
        return set(await self.session.scalars(select(days.c.day).limit(limit)))

    async def weighins(self, user_id: int, date_from: date, date_to: date) -> list[tuple[date, float]]:
        rows = await self.session.execute(
            select(BodyMetrics.measured_on, BodyMetrics.weight_kg)
            .where(BodyMetrics.user_id == user_id, BodyMetrics.deleted_at.is_(None),
                   BodyMetrics.measured_on >= date_from, BodyMetrics.measured_on <= date_to)
            .order_by(BodyMetrics.measured_on))
        return [(d, float(w)) for d, w in rows]

    async def workout_dates(self, user_id: int, date_from: date, date_to: date) -> list[date]:
        return list(await self.session.scalars(
            select(WorkoutLog.performed_on).where(
                WorkoutLog.user_id == user_id, WorkoutLog.deleted_at.is_(None),
                WorkoutLog.performed_on >= date_from, WorkoutLog.performed_on <= date_to)
            .order_by(WorkoutLog.performed_on, WorkoutLog.id)))

    async def completed_sets(self, user_id: int, date_from: date, date_to: date) -> list[LoggedSet]:
        rows = await self.session.execute(
            select(WorkoutLog.id, WorkoutLog.performed_on, WorkoutSetLog.exercise_id, Exercise.name,
                   WorkoutSetLog.set_number, WorkoutSetLog.reps, WorkoutSetLog.weight_kg)
            .join(WorkoutSetLog, WorkoutSetLog.workout_log_id == WorkoutLog.id)
            .join(Exercise, Exercise.id == WorkoutSetLog.exercise_id)
            .where(WorkoutLog.user_id == user_id, WorkoutLog.deleted_at.is_(None),
                   WorkoutLog.performed_on >= date_from, WorkoutLog.performed_on <= date_to,
                   WorkoutSetLog.completed, WorkoutSetLog.weight_kg > 0)
            .order_by(WorkoutLog.performed_on, WorkoutLog.id, WorkoutSetLog.exercise_id, WorkoutSetLog.set_number))
        return [LoggedSet(*row) for row in rows]

    async def daily_calories(self, user_id: int, date_from: date, date_to: date) -> dict[date, float]:
        rows = await self.session.execute(
            select(NutritionLog.log_date, func.sum(NutritionLog.actual_calories))
            .where(NutritionLog.user_id == user_id, NutritionLog.deleted_at.is_(None),
                   NutritionLog.log_date >= date_from, NutritionLog.log_date <= date_to)
            .group_by(NutritionLog.log_date))
        return {d: float(kcal) for d, kcal in rows}
