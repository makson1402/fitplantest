"""Training plan generation and lifecycle (B-11; FR-P1, FR-P2, FR-P3, FR-P7). Rules: docs/algorithms.md section 4."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.constants import EQUIPMENT, LEVELS, PLAN_DURATION_DAYS
from app.domain.training import InsufficientExercises, eligible_exercises, generate_training_plan
from app.repositories import UnitOfWork, UserRecord
from app.repositories.training import (
    NewSession,
    NewSessionExercise,
    PlanRecord,
    SessionExerciseContext,
    SessionExerciseRecord,
)
from app.schemas import training as s
from app.schemas.library import MuscleGroupRef
from app.services.library import exercise_summary

GOAL_NAMES = {
    "weight_loss": "Weight loss", "muscle_gain": "Muscle gain", "strength": "Strength",
    "maintenance": "Maintenance", "general_fitness": "General fitness", "endurance": "Endurance",
}


def plan_name(goal: str, days: int) -> str:
    return f"{GOAL_NAMES[goal]}, {days} {'day' if days == 1 else 'days'} per week"


def serialize_exercise(e: SessionExerciseRecord) -> s.SessionExercise:
    return s.SessionExercise(
        id=e.id, position=e.position, exercise=exercise_summary(e.exercise),
        original_exercise_id=e.original_exercise_id, planned_sets=e.planned_sets, planned_reps=e.planned_reps,
        planned_weight_kg=float(e.planned_weight_kg) if e.planned_weight_kg is not None else None,
        rest_seconds=e.rest_seconds)


def serialize(plan: PlanRecord) -> s.TrainingPlan:
    return s.TrainingPlan(
        id=plan.id, name=plan.name, goal=plan.goal, num_training_days=plan.num_training_days,
        experience_level=plan.experience_level, equipment=plan.equipment, status=plan.status,
        skipped_groups=[s.SkippedGroup(muscle_group=MuscleGroupRef(id=i, name=n), reason="injury")
                        for i, n in plan.skipped_groups],
        generated_at=plan.generated_at, start_date=plan.start_date, end_date=plan.end_date,
        sessions=[s.TrainingSession(
            id=ses.id, session_order=ses.session_order, name=ses.name, weekday=ses.weekday,
            estimated_duration_min=ses.estimated_duration_min,
            exercises=[serialize_exercise(e) for e in ses.exercises]) for ses in plan.sessions])


def insufficient(exc: InsufficientExercises) -> AppError:
    """422 `insufficient_exercises`: one detail per empty group, then the suggestions (algorithms.md 4.4)."""
    details: list[dict] = [{"field": "muscle_group", "code": "no_eligible_exercise", "muscle_group": g,
                            "message": f"No exercise available for {g} with these settings"}
                           for g in exc.empty_groups]
    if "change_equipment" in exc.suggestions:
        details.append({"code": "change_equipment", "equipment": exc.suggestions["change_equipment"],
                        "message": "Every required muscle group is covered with this equipment"})
    if "change_goal" in exc.suggestions:
        details.append({"code": "change_goal", "goals": exc.suggestions["change_goal"],
                        "message": "Every required muscle group is covered for these goals"})
    return AppError(422, "insufficient_exercises", "Not enough exercises for this plan", details)


def today_for(user: UserRecord, clock: Clock) -> date:
    """Today's date in the user's time zone (UTC when the stored name is not a valid IANA zone)."""
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return clock.now().astimezone(zone).date()


class TrainingPlanService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock

    async def generate(self, user: UserRecord, body: s.GenerateTrainingPlanRequest) -> s.TrainingPlan:
        """Create the draft plan, replacing an existing draft. On failure nothing is stored (the old draft stays)."""
        profile = await self.uow.profile.get_profile(user.id)
        if profile is None:
            raise not_found("Profile not found")  # onboarding first
        level = body.experience_level or profile.experience_level
        equipment = body.equipment or profile.equipment

        await self.uow.training.lock_user(user.id)
        exercises = await self.uow.library.domain_exercises()
        injuries = (await self.uow.library.training_context(user.id)).injuries
        try:
            plan = generate_training_plan(body.goal, body.training_days, level, equipment, exercises, injuries)
        except InsufficientExercises as exc:
            raise insufficient(exc) from exc

        group_ids = {g.name: g.id for g in await self.uow.library.muscle_groups()}
        sessions = [NewSession(
            session_order=i, name=ses.name, weekday=ses.weekday, estimated_duration_min=ses.duration_min,
            exercises=[NewSessionExercise(e.exercise_id, e.position, e.sets, e.reps, e.rest_s)
                       for e in ses.exercises]) for i, ses in enumerate(plan.sessions, start=1)]
        await self.uow.training.delete_draft(user.id)
        plan_id = await self.uow.training.create_plan(
            user.id, name=plan_name(body.goal, body.training_days), goal=body.goal,
            num_training_days=body.training_days, experience_level=level, equipment=equipment,
            skipped_group_ids=[group_ids[g] for g in plan.skipped_groups], sessions=sessions)
        await self.uow.commit()
        stored = await self.uow.training.get_plan(user.id, plan_id)
        return serialize(stored)  # type: ignore[arg-type]

    async def get_by_status(self, user: UserRecord, status: str) -> s.TrainingPlan:
        plan = await self.uow.training.get_plan_by_status(user.id, status)
        if plan is None:
            raise not_found("No such plan")
        return serialize(plan)

    async def accept(self, user: UserRecord, plan_id: int, body: s.AcceptPlanRequest | None) -> s.TrainingPlan:
        """The draft becomes active, the previous active plan is archived (FR-P7, algorithms.md 4.8)."""
        await self.uow.training.lock_user(user.id)
        plan = await self.uow.training.get_plan(user.id, plan_id)
        if plan is None:
            raise not_found("Plan not found")
        if plan.status != "draft":
            raise AppError(409, "conflict", f"Only a draft plan can be accepted (this plan is {plan.status})")
        start = (body.start_date if body and body.start_date else None) or today_for(user, self.clock)
        await self.uow.training.archive_active(user.id)
        await self.uow.training.activate(user.id, plan_id, start, start + timedelta(days=PLAN_DURATION_DAYS))
        await self.uow.commit()
        return serialize(await self.uow.training.get_plan(user.id, plan_id))  # type: ignore[arg-type]

    # ------------------------------------------------------------------ planned exercises (FR-P7, FR-A1)
    async def _editable(self, user: UserRecord, session_exercise_id: int) -> SessionExerciseContext:
        """A planned exercise of the user's draft or active plan; archived plans are history."""
        await self.uow.training.lock_user(user.id)
        context = await self.uow.training.get_session_exercise(user.id, session_exercise_id)
        if context is None:
            raise not_found("Planned exercise not found")
        if context.plan_status == "archived":
            raise AppError(409, "conflict", "An archived plan cannot be changed")
        return context

    async def update_exercise(self, user: UserRecord, session_exercise_id: int,
                              body: s.SessionExerciseUpdate) -> s.SessionExercise:
        """Edit sets, reps, weight or rest; only the fields the client sent change."""
        context = await self._editable(user, session_exercise_id)
        changes = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
        if changes.get("planned_weight_kg") is not None:
            changes["planned_weight_kg"] = Decimal(str(changes["planned_weight_kg"])).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        await self.uow.training.update_session_exercise(context.record.id, changes)
        await self.uow.commit()
        updated = await self.uow.training.get_session_exercise(user.id, session_exercise_id)
        return serialize_exercise(updated.record)  # type: ignore[union-attr]

    async def swap_exercise(self, user: UserRecord, session_exercise_id: int,
                            body: s.SwapRequest) -> s.SessionExercise:
        """Replace the exercise by an alternative of the same muscle group (algorithms.md 4.9).

        Level and equipment are those of the plan (its snapshot), injuries are the user's current active ones.
        Sets, reps, rest and weight are kept; `original_exercise_id` remembers the generated exercise."""
        context = await self._editable(user, session_exercise_id)
        exercises = await self.uow.library.domain_exercises()
        by_id = {e.id: e for e in exercises}
        current, candidate = by_id[context.record.exercise.id], by_id.get(body.exercise_id)
        injuries = (await self.uow.library.training_context(user.id)).injuries
        refusal = self._swap_refusal(current, candidate, context, exercises, injuries)
        if refusal is not None:
            raise AppError(422, "invalid_swap", "This exercise cannot replace the planned one", [
                {"field": "exercise_id", "code": refusal[0], "message": refusal[1]}])
        original = context.record.original_exercise_id or current.id
        await self.uow.training.update_session_exercise(context.record.id, {
            "exercise_id": candidate.id,  # type: ignore[union-attr]
            "original_exercise_id": None if candidate.id == original else original})  # type: ignore[union-attr]
        await self.uow.commit()
        updated = await self.uow.training.get_session_exercise(user.id, session_exercise_id)
        return serialize_exercise(updated.record)  # type: ignore[union-attr]

    @staticmethod
    def _swap_refusal(current, candidate, context: SessionExerciseContext, exercises, injuries):
        """(code, message) of the first rule the candidate breaks, None when the swap is allowed."""
        if candidate is None:
            return "unknown_exercise", "No such exercise"
        if candidate.id == current.id:
            return "same_exercise", "This is the exercise already planned"
        if candidate.main_group != current.main_group:
            return "other_muscle_group", f"Must train {current.main_group}, not {candidate.main_group}"
        if candidate.id in context.session_exercise_ids:
            return "already_in_session", "The session already contains this exercise"
        level, equipment = context.plan_experience_level, context.plan_equipment
        if candidate.id not in {e.id for e in eligible_exercises(exercises, level, equipment, injuries)}:
            if LEVELS.index(candidate.difficulty) > LEVELS.index(level):
                return "above_level", f"Too difficult for a {level} plan"
            if EQUIPMENT.index(candidate.equipment) > EQUIPMENT.index(equipment):
                return "needs_equipment", f"Needs {candidate.equipment} equipment, the plan uses {equipment}"
            return "excluded_by_injury", "Excluded by an active injury"
        return None
