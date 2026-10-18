"""Progress reports: generation, storage, listing (B-25; FR-R1, FR-R2, FR-R4, FR-R5, FR-R6). Rules: algorithms.md 7-9.

A report freezes the figures of one period: the same numbers the analytics endpoints compute for that range, plus the
chart series and key lifts that the export shows. Generating the same period again replaces the stored report.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.compliance import has_enough_data
from app.domain.constants import MAX_REPORT_DAYS, MIN_DATA_DAYS, PLAN_DURATION_DAYS
from app.domain.reports import classify_period
from app.repositories import UnitOfWork, UserRecord
from app.repositories.reports import ReportRecord
from app.schemas import reports as s
from app.services.analytics import AnalyticsService, weeks
from app.services.training import today_for

SMALLINT_MAX = 32767


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def _num(value) -> float | None:
    return None if value is None else float(value)


def to_schema(r: ReportRecord) -> s.Report:
    return s.Report(
        id=r.id, report_type=r.report_type, period_start=r.period_start, period_end=r.period_end,
        weight_difference_kg=_num(r.weight_difference_kg), training_volume_kg=float(r.training_volume_kg),
        training_sessions_completed=r.training_sessions_completed,
        training_sessions_planned=r.training_sessions_planned,
        workout_compliance_pct=_num(r.workout_compliance_pct), diet_compliance_pct=_num(r.diet_compliance_pct),
        avg_daily_calories=r.avg_daily_calories, estimated_goal_completion_date=r.estimated_goal_completion_date,
        irregular_data=r.irregular_data, is_auto=r.is_auto, details=r.details, generated_at=r.generated_at)


class ReportService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.analytics = AnalyticsService(uow, clock)

    async def create(self, user: UserRecord, body: s.CreateReportRequest, *, is_auto: bool = False) -> s.Report:
        values = await self._figures(user, body.period_start, body.period_end)
        values["is_auto"] = is_auto
        # one report per user at a time: two concurrent requests for a period must not interleave their upserts
        await self.uow.training.lock_user(user.id)
        record = await self.uow.reports.upsert(user.id, values)
        await self.uow.commit()
        return to_schema(record)

    async def create_auto(self, user: UserRecord, start: date, end: date) -> ReportRecord | None:
        """The scheduled report of FR-R7 (algorithms.md 12). Inserts only when the period has no report yet and
        returns the new one, otherwise None: a second run of the job changes nothing. Not enough history (section 8)
        also gives None. The caller commits, so it can add the notification in the same transaction."""
        await self.uow.training.lock_user(user.id)
        if await self.uow.reports.exists(user.id, classify_period(start, end), start, end):
            return None  # cheaper than computing the figures; the insert below still guards against a race
        try:
            values = await self._figures(user, start, end)
        except AppError as exc:
            if exc.code == "insufficient_data":
                return None
            raise
        values["is_auto"] = True
        return await self.uow.reports.insert_if_absent(user.id, values)

    async def list(self, user: UserRecord, report_type: str | None, limit: int, offset: int) -> s.ReportPage:
        records, total = await self.uow.reports.list(user.id, report_type, limit, offset)
        return s.ReportPage(items=[to_schema(r) for r in records], total=total, limit=limit, offset=offset)

    async def get(self, user: UserRecord, report_id: int) -> s.Report:
        return to_schema(await self.record(user, report_id))

    async def record(self, user: UserRecord, report_id: int) -> ReportRecord:
        record = await self.uow.reports.get(user.id, report_id)
        if record is None:
            raise not_found("Report not found")
        return record

    # ------------------------------------------------------------------ figures
    def _check_period(self, user: UserRecord, start: date, end: date) -> None:
        problems = []
        if end > today_for(user, self.clock):
            problems.append({"field": "period_end", "code": "in_future", "message": "The period must have started "
                             "and ended up to today"})
        if (end - start).days + 1 > MAX_REPORT_DAYS:
            problems.append({"field": "period_end", "code": "out_of_range",
                             "message": f"A report covers at most {MAX_REPORT_DAYS} days"})
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)

    async def _figures(self, user: UserRecord, start: date, end: date) -> dict:
        self._check_period(user, start, end)
        if not has_enough_data(await self.analytics.repo.record_days(user.id, MIN_DATA_DAYS)):
            raise AppError(422, "insufficient_data", "Reports need at least 7 days with records", [
                {"field": "period_start", "code": "insufficient_data",
                 "message": f"The history has fewer than {MIN_DATA_DAYS} days with a workout, a meal or a weigh-in"}])
        repo = self.analytics.repo
        weighins = await repo.weighins(user.id, start, end)
        workout_days = await repo.workout_dates(user.id, start, end)
        sets = await repo.completed_sets(user.id, start, end)
        calories = await repo.daily_calories(user.id, start, end)
        prediction = await self.analytics.goal_prediction(user)

        per_day: dict[date, float] = defaultdict(float)
        for x in sets:
            per_day[x.performed_on] += float(x.weight_kg) * x.reps
        details = {
            "charts": {
                "weight": [{"date": d.isoformat(), "value": v} for d, v in weighins],
                "tonnage": [{"date": d.isoformat(), "value": _round(v)} for d, v in sorted(per_day.items())],
                "calories": [{"date": d.isoformat(), "value": _round(v, 1)} for d, v in sorted(calories.items())],
                "workouts_per_week": [
                    {"date": a.isoformat(), "value": float(sum(1 for d in workout_days if a <= d <= b))}
                    for a, b in weeks(start, end)],
            },
            "key_lifts": [lift.model_dump() for lift in self.analytics.key_lifts(sets)],
            "goal_prediction": {
                "status": prediction.status, "slope_kg_per_week": prediction.slope_kg_per_week, "r2": prediction.r2,
                "target_weight_kg": prediction.target_weight_kg, "warnings": prediction.warnings},
        }
        return {
            "report_type": classify_period(start, end), "period_start": start, "period_end": end,
            "weight_difference_kg": _round(weighins[-1][1] - weighins[0][1]) if len(weighins) >= 2 else None,
            "training_volume_kg": _round(sum(float(x.weight_kg) * x.reps for x in sets)) or 0,
            "training_sessions_completed": min(len(workout_days), SMALLINT_MAX),
            "training_sessions_planned": await self._planned_sessions(user, start, end),
            "workout_compliance_pct": await self.analytics.training_compliance(user, start, end, workout_days),
            "diet_compliance_pct": await self.analytics.diet_compliance_pct(user, start, end, calories),
            "avg_daily_calories": round(sum(calories.values()) / len(calories)) if calories else None,
            "estimated_goal_completion_date": prediction.estimated_date if prediction.status == "ok" else None,
            "irregular_data": bool(prediction.warnings),
            "details": details,
        }

    async def _planned_sessions(self, user: UserRecord, start: date, end: date) -> int:
        """Sessions per week of the active plan x the days of the period it covers / 7 (the compliance denominator)."""
        plan = await self.uow.training.get_plan_by_status(user.id, "active")
        if plan is None or plan.start_date is None:
            return 0
        first = max(start, plan.start_date)
        last = min(end, plan.end_date or plan.start_date + timedelta(days=PLAN_DURATION_DAYS))
        if first > last:
            return 0
        return min(round(len(plan.sessions) * ((last - first).days + 1) / 7), SMALLINT_MAX)
