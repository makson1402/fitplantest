"""SQLAlchemy implementation of `WorkoutRepository` (B-15, B-16)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reference import Exercise, MuscleGroup
from app.db.models.training import (
    PersonalRecord,
    PlanAdjustment,
    SessionExercise,
    TrainingPlan,
    TrainingSession,
    WorkoutLog,
    WorkoutSetLog,
)
from app.repositories.sql_library import _exercise
from app.repositories.training import SessionExerciseRecord
from app.repositories.workouts import (
    AdjustmentRecord,
    PersonalRecordRecord,
    PlannedForAdaptation,
    SessionForAdaptation,
    SetRecord,
    WorkoutRecord,
)


def _set(row: WorkoutSetLog) -> SetRecord:
    return SetRecord(exercise_id=row.exercise_id, set_number=row.set_number, reps=row.reps, weight_kg=row.weight_kg,
                     rpe=row.rpe, completed=row.completed, session_exercise_id=row.session_exercise_id, id=row.id)


def _workout(row: WorkoutLog, sets: list[SetRecord]) -> WorkoutRecord:
    return WorkoutRecord(
        id=row.id, user_id=row.user_id, client_uuid=row.client_uuid, training_session_id=row.training_session_id,
        performed_on=row.performed_on, started_at=row.started_at, finished_at=row.finished_at,
        overall_rpe=row.overall_rpe, notes=row.notes, created_at=row.created_at, updated_at=row.updated_at,
        deleted_at=row.deleted_at, sets=sets)


class SqlWorkoutRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ helpers
    async def _sets(self, workout_ids: list[int]) -> dict[int, list[SetRecord]]:
        out: dict[int, list[SetRecord]] = {i: [] for i in workout_ids}
        if workout_ids:
            rows = await self.session.scalars(
                select(WorkoutSetLog).where(WorkoutSetLog.workout_log_id.in_(workout_ids))
                .order_by(WorkoutSetLog.workout_log_id, WorkoutSetLog.exercise_id, WorkoutSetLog.set_number))
            for row in rows:
                out[row.workout_log_id].append(_set(row))
        return out

    async def _insert_sets(self, workout_id: int, sets: list[SetRecord]) -> list[SetRecord]:
        stored = []
        for s in sets:
            row_id = await self.session.scalar(insert(WorkoutSetLog).values(
                workout_log_id=workout_id, exercise_id=s.exercise_id, session_exercise_id=s.session_exercise_id,
                set_number=s.set_number, reps=s.reps, weight_kg=s.weight_kg, rpe=s.rpe,
                completed=s.completed).returning(WorkoutSetLog.id))
            stored.append(SetRecord(s.exercise_id, s.set_number, s.reps, s.weight_kg, s.rpe, s.completed,
                                    s.session_exercise_id, row_id))
        return stored

    # ------------------------------------------------------------------ lookups
    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> WorkoutRecord | None:
        row = await self.session.scalar(select(WorkoutLog).where(
            WorkoutLog.user_id == user_id, WorkoutLog.client_uuid == client_uuid)
            .execution_options(populate_existing=True))
        return _workout(row, (await self._sets([row.id]))[row.id]) if row else None

    async def existing_exercise_ids(self, ids: list[int]) -> set[int]:
        return set(await self.session.scalars(select(Exercise.id).where(Exercise.id.in_(ids)))) if ids else set()

    async def session_for_adaptation(self, user_id: int, session_id: int) -> SessionForAdaptation | None:
        plan_status = await self.session.scalar(
            select(TrainingPlan.status).join(TrainingSession, TrainingSession.training_plan_id == TrainingPlan.id)
            .where(TrainingSession.id == session_id, TrainingPlan.user_id == user_id))
        if plan_status is None:
            return None
        rows = await self.session.execute(
            select(SessionExercise, Exercise, MuscleGroup.name, MuscleGroup.body_region)
            .join(Exercise, Exercise.id == SessionExercise.exercise_id)
            .join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
            .where(SessionExercise.training_session_id == session_id).order_by(SessionExercise.position)
            .execution_options(populate_existing=True))
        exercises = [
            PlannedForAdaptation(
                SessionExerciseRecord(se.id, se.position, _exercise(ex, group), se.original_exercise_id,
                                      se.planned_sets, se.planned_reps, se.planned_weight_kg, se.rest_seconds),
                ex.is_bodyweight, region)
            for se, ex, group, region in rows]
        return SessionForAdaptation(session_id, plan_status, exercises)

    # ------------------------------------------------------------------ workouts
    async def create_workout(self, user_id: int, values: dict, sets: list[SetRecord]) -> WorkoutRecord:
        row = await self.session.scalar(
            insert(WorkoutLog).values(user_id=user_id, **values).returning(WorkoutLog),
            execution_options={"populate_existing": True})
        return _workout(row, await self._insert_sets(row.id, sets))

    async def get_workout(self, user_id: int, workout_id: int) -> WorkoutRecord | None:
        row = await self.session.scalar(select(WorkoutLog).where(
            WorkoutLog.id == workout_id, WorkoutLog.user_id == user_id, WorkoutLog.deleted_at.is_(None))
            .execution_options(populate_existing=True))
        return _workout(row, (await self._sets([row.id]))[row.id]) if row else None

    async def list_workouts(self, user_id: int, date_from: date | None, date_to: date | None, limit: int,
                            offset: int) -> tuple[list[WorkoutRecord], int]:
        conditions = [WorkoutLog.user_id == user_id, WorkoutLog.deleted_at.is_(None)]
        if date_from is not None:
            conditions.append(WorkoutLog.performed_on >= date_from)
        if date_to is not None:
            conditions.append(WorkoutLog.performed_on <= date_to)
        total = await self.session.scalar(select(func.count()).select_from(WorkoutLog).where(*conditions))
        rows = list(await self.session.scalars(
            select(WorkoutLog).where(*conditions).order_by(WorkoutLog.performed_on.desc(), WorkoutLog.id.desc())
            .limit(limit).offset(offset).execution_options(populate_existing=True)))
        sets = await self._sets([r.id for r in rows])
        return [_workout(r, sets[r.id]) for r in rows], total or 0

    async def replace_workout(self, user_id: int, workout_id: int, values: dict,
                              sets: list[SetRecord]) -> WorkoutRecord | None:
        row = await self.session.scalar(
            update(WorkoutLog).where(WorkoutLog.id == workout_id, WorkoutLog.user_id == user_id,
                                     WorkoutLog.deleted_at.is_(None)).values(**values).returning(WorkoutLog),
            execution_options={"populate_existing": True})
        if row is None:
            return None
        await self.session.execute(delete(WorkoutSetLog).where(WorkoutSetLog.workout_log_id == workout_id))
        return _workout(row, await self._insert_sets(workout_id, sets))

    async def soft_delete(self, user_id: int, workout_id: int, at: datetime) -> bool:
        done = await self.session.scalar(
            update(WorkoutLog).where(WorkoutLog.id == workout_id, WorkoutLog.user_id == user_id,
                                     WorkoutLog.deleted_at.is_(None)).values(deleted_at=at)
            .returning(WorkoutLog.id))
        return done is not None

    async def has_workout(self, user_id: int, session_id: int, performed_on: date) -> bool:
        found = await self.session.scalar(select(WorkoutLog.id).where(
            WorkoutLog.user_id == user_id, WorkoutLog.training_session_id == session_id,
            WorkoutLog.performed_on == performed_on, WorkoutLog.deleted_at.is_(None)).limit(1))
        return found is not None

    # ------------------------------------------------------------------ adjustments
    async def add_adjustment(self, session_exercise_id: int, workout_id: int, reason: str,
                             old: tuple[int, int, Decimal | None], new: tuple[int, int, Decimal | None]) -> None:
        await self.session.execute(insert(PlanAdjustment).values(
            session_exercise_id=session_exercise_id, workout_log_id=workout_id, reason=reason,
            old_sets=old[0], old_reps=old[1], old_weight_kg=old[2],
            new_sets=new[0], new_reps=new[1], new_weight_kg=new[2]))

    async def adjustments_of(self, workout_id: int) -> list[AdjustmentRecord]:
        rows = await self.session.execute(
            select(PlanAdjustment, SessionExercise.exercise_id, Exercise.name)
            .join(SessionExercise, SessionExercise.id == PlanAdjustment.session_exercise_id)
            .join(Exercise, Exercise.id == SessionExercise.exercise_id)
            .where(PlanAdjustment.workout_log_id == workout_id).order_by(PlanAdjustment.id))
        return [AdjustmentRecord(a.session_exercise_id, exercise_id, name, a.reason, a.old_sets, a.new_sets,
                                 a.old_reps, a.new_reps, a.old_weight_kg, a.new_weight_kg)
                for a, exercise_id, name in rows]

    # ------------------------------------------------------------------ personal records
    async def current_e1rm(self, user_id: int, exercise_id: int) -> float | None:
        value = await self.session.scalar(select(PersonalRecord.estimated_1rm_kg).where(
            PersonalRecord.user_id == user_id, PersonalRecord.exercise_id == exercise_id, PersonalRecord.is_current))
        return float(value) if value is not None else None

    async def replace_record(self, user_id: int, exercise_id: int, *, weight: Decimal, reps: int, e1rm: Decimal,
                             achieved_on: date, source_set_id: int | None) -> None:
        # the partial unique index allows one current record: retire the old one first
        await self.session.execute(update(PersonalRecord).where(
            PersonalRecord.user_id == user_id, PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.is_current).values(is_current=False))
        await self.session.execute(insert(PersonalRecord).values(
            user_id=user_id, exercise_id=exercise_id, max_weight_kg=weight, max_reps=reps, estimated_1rm_kg=e1rm,
            achieved_on=achieved_on, is_current=True, source_set_id=source_set_id))

    async def records_of(self, workout_id: int) -> list[PersonalRecordRecord]:
        rows = await self.session.execute(
            select(PersonalRecord, Exercise.name)
            .join(Exercise, Exercise.id == PersonalRecord.exercise_id)
            .join(WorkoutSetLog, WorkoutSetLog.id == PersonalRecord.source_set_id)
            .where(WorkoutSetLog.workout_log_id == workout_id).order_by(Exercise.name))
        return [PersonalRecordRecord(r.exercise_id, name, r.max_weight_kg, r.max_reps, r.estimated_1rm_kg,
                                     r.achieved_on) for r, name in rows]

    async def current_records(self, user_id: int) -> list[PersonalRecordRecord]:
        rows = await self.session.execute(
            select(PersonalRecord, Exercise.name).join(Exercise, Exercise.id == PersonalRecord.exercise_id)
            .where(PersonalRecord.user_id == user_id, PersonalRecord.is_current).order_by(Exercise.name))
        return [PersonalRecordRecord(r.exercise_id, name, r.max_weight_kg, r.max_reps, r.estimated_1rm_kg,
                                     r.achieved_on) for r, name in rows]
