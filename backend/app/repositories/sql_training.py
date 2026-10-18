"""SQLAlchemy implementation of `TrainingRepository` (B-11)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import User
from app.db.models.reference import Exercise, MuscleGroup
from app.db.models.training import SessionExercise, TrainingPlan, TrainingSession
from app.repositories.sql_library import _exercise
from app.repositories.training import (
    NewSession,
    PlanRecord,
    SessionExerciseContext,
    SessionExerciseRecord,
    SessionRecord,
)


class SqlTrainingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_user(self, user_id: int) -> None:
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def delete_draft(self, user_id: int) -> None:
        # sessions, exercises and adjustments go with the plan (ON DELETE CASCADE)
        await self.session.execute(
            delete(TrainingPlan).where(TrainingPlan.user_id == user_id, TrainingPlan.status == "draft"))

    async def create_plan(self, user_id: int, *, name: str, goal: str, num_training_days: int,
                          experience_level: str, equipment: str, skipped_group_ids: list[int],
                          sessions: list[NewSession]) -> int:
        plan_id = await self.session.scalar(insert(TrainingPlan).values(
            user_id=user_id, name=name, goal=goal, num_training_days=num_training_days,
            experience_level=experience_level, equipment=equipment, skipped_muscle_group_ids=skipped_group_ids,
            status="draft").returning(TrainingPlan.id))
        for s in sessions:
            session_id = await self.session.scalar(insert(TrainingSession).values(
                training_plan_id=plan_id, session_order=s.session_order, name=s.name, weekday=s.weekday,
                estimated_duration_min=s.estimated_duration_min).returning(TrainingSession.id))
            if s.exercises:
                await self.session.execute(insert(SessionExercise), [
                    {"training_session_id": session_id, "exercise_id": e.exercise_id, "position": e.position,
                     "planned_sets": e.sets, "planned_reps": e.reps, "rest_seconds": e.rest_seconds}
                    for e in s.exercises])
        return plan_id

    async def get_plan(self, user_id: int, plan_id: int) -> PlanRecord | None:
        return await self._load(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)

    async def get_plan_by_status(self, user_id: int, status: str) -> PlanRecord | None:
        return await self._load(TrainingPlan.user_id == user_id, TrainingPlan.status == status)

    async def get_session_exercise(self, user_id: int, session_exercise_id: int) -> SessionExerciseContext | None:
        row = (await self.session.execute(
            select(SessionExercise, Exercise, MuscleGroup.name, TrainingSession, TrainingPlan)
            .join(Exercise, Exercise.id == SessionExercise.exercise_id)
            .join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
            .join(TrainingSession, TrainingSession.id == SessionExercise.training_session_id)
            .join(TrainingPlan, TrainingPlan.id == TrainingSession.training_plan_id)
            .where(SessionExercise.id == session_exercise_id, TrainingPlan.user_id == user_id)
            .execution_options(populate_existing=True))).first()
        if row is None:
            return None
        se, exercise, group, session, plan = row
        siblings = list(await self.session.scalars(
            select(SessionExercise.exercise_id).where(SessionExercise.training_session_id == session.id)))
        record = SessionExerciseRecord(se.id, se.position, _exercise(exercise, group), se.original_exercise_id,
                                       se.planned_sets, se.planned_reps, se.planned_weight_kg, se.rest_seconds)
        return SessionExerciseContext(record, plan.id, plan.status, plan.experience_level, plan.equipment,
                                      session.id, siblings)

    async def session_plan(self, user_id: int, session_id: int) -> tuple[int, str] | None:
        row = (await self.session.execute(
            select(TrainingPlan.id, TrainingPlan.status)
            .join(TrainingSession, TrainingSession.training_plan_id == TrainingPlan.id)
            .where(TrainingSession.id == session_id, TrainingPlan.user_id == user_id))).first()
        return (row[0], row[1]) if row else None

    async def set_session_weekday(self, session_id: int, weekday: str) -> None:
        await self.session.execute(update(TrainingSession).where(TrainingSession.id == session_id).values(
            weekday=weekday))

    async def update_session_exercise(self, session_exercise_id: int, changes: dict) -> None:
        if changes:
            await self.session.execute(
                update(SessionExercise).where(SessionExercise.id == session_exercise_id).values(**changes))

    async def archive_active(self, user_id: int) -> None:
        await self.session.execute(update(TrainingPlan).where(
            TrainingPlan.user_id == user_id, TrainingPlan.status == "active").values(status="archived"))

    async def activate(self, user_id: int, plan_id: int, start_date: date, end_date: date) -> None:
        await self.session.execute(update(TrainingPlan).where(
            TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id).values(
            status="active", start_date=start_date, end_date=end_date))

    async def _load(self, *conditions) -> PlanRecord | None:
        plan = await self.session.scalar(
            select(TrainingPlan).where(*conditions).execution_options(populate_existing=True))
        if plan is None:
            return None
        skipped = []
        if plan.skipped_muscle_group_ids:
            rows = await self.session.execute(
                select(MuscleGroup.id, MuscleGroup.name).where(MuscleGroup.id.in_(plan.skipped_muscle_group_ids))
                .order_by(MuscleGroup.id))
            skipped = [(gid, name) for gid, name in rows]
        record = PlanRecord(
            id=plan.id, user_id=plan.user_id, name=plan.name, goal=plan.goal,
            num_training_days=plan.num_training_days, experience_level=plan.experience_level,
            equipment=plan.equipment, status=plan.status, skipped_groups=skipped, generated_at=plan.generated_at,
            start_date=plan.start_date, end_date=plan.end_date)
        sessions = {}
        for s in await self.session.scalars(select(TrainingSession).where(TrainingSession.training_plan_id == plan.id)
                                            .order_by(TrainingSession.session_order)):
            sessions[s.id] = SessionRecord(s.id, s.session_order, s.name, s.weekday, s.estimated_duration_min)
            record.sessions.append(sessions[s.id])
        if sessions:
            rows = await self.session.execute(
                select(SessionExercise, Exercise, MuscleGroup.name)
                .join(Exercise, Exercise.id == SessionExercise.exercise_id)
                .join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
                .where(SessionExercise.training_session_id.in_(sessions)).order_by(SessionExercise.position))
            for se, exercise, group in rows:
                sessions[se.training_session_id].exercises.append(SessionExerciseRecord(
                    se.id, se.position, _exercise(exercise, group), se.original_exercise_id, se.planned_sets,
                    se.planned_reps, se.planned_weight_kg, se.rest_seconds))
        return record
