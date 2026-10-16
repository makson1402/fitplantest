"""Training plan generation and lifecycle (B-11; FR-P1, FR-P2, FR-P3, FR-P7). Rules: docs/algorithms.md section 4."""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.constants import PLAN_DURATION_DAYS
from app.domain.training import InsufficientExercises, generate_training_plan
from app.repositories import UnitOfWork, UserRecord
from app.repositories.training import NewSession, NewSessionExercise, PlanRecord
from app.schemas import training as s
from app.schemas.library import MuscleGroupRef
from app.services.library import exercise_summary

GOAL_NAMES = {
    "weight_loss": "Weight loss", "muscle_gain": "Muscle gain", "strength": "Strength",
    "maintenance": "Maintenance", "general_fitness": "General fitness", "endurance": "Endurance",
}


def plan_name(goal: str, days: int) -> str:
    return f"{GOAL_NAMES[goal]}, {days} {'day' if days == 1 else 'days'} per week"


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
            exercises=[s.SessionExercise(
                id=e.id, position=e.position, exercise=exercise_summary(e.exercise),
                original_exercise_id=e.original_exercise_id, planned_sets=e.planned_sets,
                planned_reps=e.planned_reps,
                planned_weight_kg=float(e.planned_weight_kg) if e.planned_weight_kg is not None else None,
                rest_seconds=e.rest_seconds) for e in ses.exercises]) for ses in plan.sessions])


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


def _today(user: UserRecord, clock: Clock) -> date:
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
        start = (body.start_date if body and body.start_date else None) or _today(user, self.clock)
        await self.uow.training.archive_active(user.id)
        await self.uow.training.activate(user.id, plan_id, start, start + timedelta(days=PLAN_DURATION_DAYS))
        await self.uow.commit()
        return serialize(await self.uow.training.get_plan(user.id, plan_id))  # type: ignore[arg-type]
