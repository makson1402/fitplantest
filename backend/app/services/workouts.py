"""Workout logging, plan adaptation and personal records (B-15, B-16; FR-A2, A3, A4, A5). Rules: algorithms.md 6."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.adaptation import SetLog, adapt, best_new_record
from app.repositories import UnitOfWork, UserRecord
from app.repositories.workouts import (
    AdjustmentRecord,
    PersonalRecordRecord,
    SessionForAdaptation,
    SetRecord,
    WorkoutRecord,
)
from app.schemas import workouts as s
from app.services.training import serialize_session, today_for

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday(): Monday is 0
ADAPTED_PLAN_STATUSES = ("draft", "active")  # an archived plan is history: its values are not adapted
_TWO = Decimal("0.01")


def _dec(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_TWO, rounding=ROUND_HALF_UP)


def _problem(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def serialize_workout(w: WorkoutRecord) -> s.Workout:
    return s.Workout(
        id=w.id, client_uuid=w.client_uuid, training_session_id=w.training_session_id, performed_on=w.performed_on,
        started_at=w.started_at, finished_at=w.finished_at, overall_rpe=w.overall_rpe, notes=w.notes,
        created_at=w.created_at, updated_at=w.updated_at,
        sets=[s.WorkoutSetInput(exercise_id=x.exercise_id, session_exercise_id=x.session_exercise_id,
                                set_number=x.set_number, reps=x.reps, weight_kg=float(x.weight_kg), rpe=x.rpe,
                                completed=x.completed) for x in w.sets])


def _adjustment(a: AdjustmentRecord) -> s.PlanAdjustment:
    def num(v):
        return float(v) if v is not None else None
    return s.PlanAdjustment(
        session_exercise_id=a.session_exercise_id, exercise_id=a.exercise_id, exercise_name=a.exercise_name,
        reason=a.reason, old_sets=a.old_sets, new_sets=a.new_sets, old_reps=a.old_reps, new_reps=a.new_reps,
        old_weight_kg=num(a.old_weight_kg), new_weight_kg=num(a.new_weight_kg))


def _record(r: PersonalRecordRecord) -> s.PersonalRecord:
    return s.PersonalRecord(exercise_id=r.exercise_id, exercise_name=r.exercise_name,
                            max_weight_kg=float(r.max_weight_kg), max_reps=r.max_reps,
                            estimated_1rm_kg=float(r.estimated_1rm_kg), achieved_on=r.achieved_on)


def _set_records(body: s.WorkoutInput) -> list[SetRecord]:
    return [SetRecord(exercise_id=x.exercise_id, set_number=x.set_number, reps=x.reps, weight_kg=_dec(x.weight_kg),
                      rpe=x.rpe, completed=x.completed, session_exercise_id=x.session_exercise_id)
            for x in body.sets]


class WorkoutService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.repo = uow.workouts

    # ------------------------------------------------------------------ validation
    async def _validate(self, user: UserRecord, body: s.WorkoutInput) -> SessionForAdaptation | None:
        """Business checks that need the database; every problem is reported with its field path (HTTP 422)."""
        problems: list[dict] = []
        if body.performed_on > today_for(user, self.clock) + timedelta(days=1):
            problems.append(_problem("performed_on", "future_date", "A workout cannot be in the future"))
        if body.started_at and body.finished_at and body.finished_at < body.started_at:
            problems.append(_problem("finished_at", "before_start", "finished_at is before started_at"))
        seen: set[tuple[int, int]] = set()
        for i, x in enumerate(body.sets):
            if (x.exercise_id, x.set_number) in seen:
                problems.append(_problem(f"sets.{i}.set_number", "duplicate",
                                         "This set number is used twice for the exercise"))
            seen.add((x.exercise_id, x.set_number))
        known = await self.repo.existing_exercise_ids(sorted({x.exercise_id for x in body.sets}))
        problems += [_problem(f"sets.{i}.exercise_id", "not_found", "Unknown exercise")
                     for i, x in enumerate(body.sets) if x.exercise_id not in known]

        context = None
        if body.training_session_id is not None:
            context = await self.repo.session_for_adaptation(user.id, body.training_session_id)
            if context is None:
                problems.append(_problem("training_session_id", "not_found", "Unknown training session"))
        ids = {e.planned.id for e in context.exercises} if context else set()
        for i, x in enumerate(body.sets):
            if x.session_exercise_id is not None and x.session_exercise_id not in ids:
                problems.append(_problem(f"sets.{i}.session_exercise_id", "not_found",
                                         "Not an exercise of the given training session"))
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)
        return context

    # ------------------------------------------------------------------ create
    async def create(self, user: UserRecord, body: s.WorkoutInput) -> s.WorkoutResult:
        """Save a finished workout, adapt the plan (section 6) and update personal records (6.5)."""
        await self.uow.training.lock_user(user.id)  # serialise adaptation per user
        if body.client_uuid is not None:
            existing = await self.repo.find_by_client_uuid(user.id, body.client_uuid)
            if existing is not None:  # a retry: answer with what the first request produced
                if existing.deleted_at is not None:
                    raise AppError(409, "conflict", "A workout with this client_uuid was deleted")
                return await self._result(existing)
        context = await self._validate(user, body)

        workout = await self.repo.create_workout(user.id, {
            "client_uuid": body.client_uuid or uuid4(), "training_session_id": body.training_session_id,
            "performed_on": body.performed_on, "started_at": body.started_at, "finished_at": body.finished_at,
            "overall_rpe": body.overall_rpe, "notes": body.notes}, _set_records(body))
        if context is not None and context.plan_status in ADAPTED_PLAN_STATUSES:
            await self._adapt(context, workout, body.overall_rpe)
        await self._update_records(user, workout)
        await self.uow.commit()
        return await self._result(workout)

    async def _result(self, workout: WorkoutRecord) -> s.WorkoutResult:
        return s.WorkoutResult(
            workout=serialize_workout(workout),
            adjustments=[_adjustment(a) for a in await self.repo.adjustments_of(workout.id)],
            new_personal_records=[_record(r) for r in await self.repo.records_of(workout.id)])

    async def _adapt(self, context: SessionForAdaptation, workout: WorkoutRecord, overall_rpe: int | None) -> None:
        """Apply algorithms.md 6 to every planned exercise of the session that has logged sets. Without an explicit
        signal `adapt` returns None and nothing is written (FR-A4)."""
        for item in context.exercises:
            planned = item.planned
            logged = [x for x in workout.sets
                      if x.session_exercise_id == planned.id
                      or (x.session_exercise_id is None and x.exercise_id == planned.exercise.id)]
            if not logged:
                continue
            old_weight = planned.planned_weight_kg
            result = adapt(planned.planned_sets, planned.planned_reps,
                           float(old_weight) if old_weight is not None else None, item.is_bodyweight,
                           item.body_region, [SetLog(x.reps, float(x.weight_kg), x.completed, x.rpe) for x in logged],
                           overall_rpe)
            if result is None or (result.reason == "baseline" and not result.weight_kg):
                continue  # no signal, or a "baseline" from sets logged without any weight
            new = (result.sets, result.reps, _dec(result.weight_kg) if result.weight_kg is not None else None)
            old = (planned.planned_sets, planned.planned_reps, old_weight)
            if new == old:
                continue  # a signal that changes nothing (for example already at the minimum number of sets)
            await self.uow.training.update_session_exercise(planned.id, {
                "planned_sets": new[0], "planned_reps": new[1], "planned_weight_kg": new[2]})
            await self.repo.add_adjustment(planned.id, workout.id, result.reason, old, new)

    async def _update_records(self, user: UserRecord, workout: WorkoutRecord) -> None:
        """A set becomes the new record of its exercise only when its estimated 1RM beats the current one."""
        for exercise_id in sorted({x.exercise_id for x in workout.sets}):
            sets = [x for x in workout.sets if x.exercise_id == exercise_id]
            logs = [SetLog(x.reps, float(x.weight_kg), x.completed, x.rpe) for x in sets]
            best = best_new_record(logs, await self.repo.current_e1rm(user.id, exercise_id))
            if best is None:
                continue
            log, e1rm = best
            source = next(x for x, candidate in zip(sets, logs, strict=True) if candidate is log)
            await self.repo.replace_record(user.id, exercise_id, weight=_dec(log.weight_kg), reps=log.reps,
                                           e1rm=_dec(e1rm), achieved_on=workout.performed_on, source_set_id=source.id)

    # ------------------------------------------------------------------ read, replace, delete
    async def list(self, user: UserRecord, date_from: date | None, date_to: date | None, limit: int,
                   offset: int) -> s.WorkoutPage:
        records, total = await self.repo.list_workouts(user.id, date_from, date_to, limit, offset)
        return s.WorkoutPage(items=[serialize_workout(w) for w in records], total=total, limit=limit, offset=offset)

    async def get(self, user: UserRecord, workout_id: int) -> s.Workout:
        workout = await self.repo.get_workout(user.id, workout_id)
        if workout is None:
            raise not_found("Workout not found")
        return serialize_workout(workout)

    async def replace(self, user: UserRecord, workout_id: int, body: s.WorkoutInput) -> s.Workout:
        """Replace a saved workout and its sets. The plan is not adapted again and personal records are kept."""
        await self.uow.training.lock_user(user.id)
        current = await self.repo.get_workout(user.id, workout_id)
        if current is None:
            raise not_found("Workout not found")
        if body.client_uuid is not None and body.client_uuid != current.client_uuid:
            raise AppError(422, "validation_error", "Invalid input", [
                _problem("client_uuid", "immutable", "The client_uuid of a workout cannot change")])
        await self._validate(user, body)
        updated = await self.repo.replace_workout(user.id, workout_id, {
            "training_session_id": body.training_session_id, "performed_on": body.performed_on,
            "started_at": body.started_at, "finished_at": body.finished_at, "overall_rpe": body.overall_rpe,
            "notes": body.notes}, _set_records(body))
        await self.uow.commit()
        return serialize_workout(updated)  # type: ignore[arg-type]

    async def delete(self, user: UserRecord, workout_id: int) -> None:
        if not await self.repo.soft_delete(user.id, workout_id, self.clock.now()):
            raise not_found("Workout not found")
        await self.uow.commit()

    async def personal_records(self, user: UserRecord) -> list[s.PersonalRecord]:
        return [_record(r) for r in await self.repo.current_records(user.id)]

    # ------------------------------------------------------------------ next session
    async def next_session(self, user: UserRecord) -> s.NextSession:
        """The next session of the active plan that has not been trained yet (FR-A4, FR-A5).

        A session is scheduled on its weekday; the next date is today or later (and not before the plan starts); a
        date on which the session already has a workout is skipped; dates after the plan's end do not count."""
        plan = await self.uow.training.get_plan_by_status(user.id, "active")
        if plan is None:
            raise not_found("No active training plan")
        start = max(today_for(user, self.clock), plan.start_date or date.min)
        candidates = []
        for session in plan.sessions:
            day = start + timedelta(days=(WEEKDAYS.index(session.weekday) - start.weekday()) % 7)
            while (plan.end_date is None or day <= plan.end_date) and await self.repo.has_workout(
                user.id, session.id, day
            ):
                day += timedelta(days=7)
            if plan.end_date is None or day <= plan.end_date:
                candidates.append((day, session.session_order, session))
        if not candidates:
            raise not_found("The active plan has no session left")
        day, _, session = min(candidates, key=lambda c: (c[0], c[1]))
        return s.NextSession(session=serialize_session(session), scheduled_date=day)
