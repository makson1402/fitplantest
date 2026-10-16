"""Analytics, chart series and the goal prediction (B-23, B-24; FR-R1..R5). Rules: docs/algorithms.md sections 7-9."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.core.clock import Clock
from app.domain.adaptation import e1rm
from app.domain.compliance import diet_compliance, has_enough_data, workout_compliance
from app.domain.constants import MIN_DATA_DAYS, PLAN_DURATION_DAYS, PR_MAX_REPS, PREDICTION_WINDOW_DAYS
from app.domain.prediction import predict_goal
from app.repositories import UnitOfWork, UserRecord
from app.repositories.analytics import LoggedSet
from app.schemas import analytics as s
from app.services.training import today_for

PERIOD_DAYS = {"week": 7, "month": 30, "3months": 90}  # algorithms.md 8: the last N days including today
KEY_LIFTS = 3


def window(period: str, today: date) -> tuple[date, date]:
    return today - timedelta(days=PERIOD_DAYS[period] - 1), today


def weeks(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """The ISO weeks (Monday-Sunday) that overlap [date_from, date_to], each clipped to that range."""
    out, monday = [], date_from - timedelta(days=date_from.weekday())
    while monday <= date_to:
        out.append((max(monday, date_from), min(monday + timedelta(days=6), date_to)))
        monday += timedelta(days=7)
    return out


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def _counted(sets: list[LoggedSet]) -> list[LoggedSet]:
    """Sets that can show strength: 1 to 12 reps (the Epley range of algorithms.md 6.5)."""
    return [x for x in sets if 1 <= x.reps <= PR_MAX_REPS]


class AnalyticsService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.repo = uow.analytics

    async def _enough_data(self, user: UserRecord) -> bool:
        return has_enough_data(await self.repo.record_days(user.id, MIN_DATA_DAYS))

    async def _training_compliance(self, user: UserRecord, date_from: date, date_to: date,
                                   workout_days: list[date]) -> float | None:
        """Section 7: workouts done in the part of the range that the active plan covers, over the planned sessions
        (sessions per week x days / 7). None without an active plan or when the plan does not overlap the range."""
        plan = await self.uow.training.get_plan_by_status(user.id, "active")
        if plan is None or plan.start_date is None:
            return None
        start = max(date_from, plan.start_date)
        end = min(date_to, plan.end_date or plan.start_date + timedelta(days=PLAN_DURATION_DAYS))
        if start > end:
            return None
        done = sum(1 for d in workout_days if start <= d <= end)
        return workout_compliance(done, len(plan.sessions), (end - start).days + 1)

    async def _diet_compliance(self, user: UserRecord, date_from: date, date_to: date,
                               calories: dict[date, float]) -> float | None:
        """Section 7: share of days (from the start of the active diet plan) within 10 % of the calorie target."""
        plan = await self.uow.diet.get_plan_by_status(user.id, "active")
        if plan is None or plan.start_date is None:
            return None
        start = max(date_from, plan.start_date)
        end = min(date_to, plan.end_date or plan.start_date + timedelta(days=PLAN_DURATION_DAYS))
        if start > end:
            return None
        return diet_compliance(calories, plan.daily_calorie_target, start, end)

    # ------------------------------------------------------------------ summary
    async def summary(self, user: UserRecord, period: str) -> s.AnalyticsSummary:
        date_from, date_to = window(period, today_for(user, self.clock))
        base = {"period": period, "from": date_from, "to": date_to}
        if not await self._enough_data(user):
            return s.AnalyticsSummary(status="insufficient_data", **base)

        weighins = await self.repo.weighins(user.id, date_from, date_to)
        workout_days = await self.repo.workout_dates(user.id, date_from, date_to)
        sets = await self.repo.completed_sets(user.id, date_from, date_to)
        calories = await self.repo.daily_calories(user.id, date_from, date_to)
        total = len(workout_days)
        tonnage = sum(float(x.weight_kg) * x.reps for x in sets)
        return s.AnalyticsSummary(
            status="ok", **base,
            weight_change_kg=_round(weighins[-1][1] - weighins[0][1]) if len(weighins) >= 2 else None,
            total_workouts=total or None,
            avg_workouts_per_week=_round(total / (PERIOD_DAYS[period] / 7)) if total else None,
            avg_calories=_round(sum(calories.values()) / len(calories), 1) if calories else None,
            tonnage_kg=_round(tonnage) if sets else None,
            workout_compliance_pct=await self._training_compliance(user, date_from, date_to, workout_days),
            diet_compliance_pct=await self._diet_compliance(user, date_from, date_to, calories),
            key_lifts=self._key_lifts(sets))

    @staticmethod
    def _key_lifts(sets: list[LoggedSet]) -> list[s.KeyLift]:
        """The three most-trained exercises (most workouts, then most sets): e1RM of the first and the best set."""
        by_exercise: dict[int, list[LoggedSet]] = defaultdict(list)
        for x in _counted(sets):
            by_exercise[x.exercise_id].append(x)
        ranked = sorted(by_exercise.items(),
                        key=lambda kv: (-len({x.workout_id for x in kv[1]}), -len(kv[1]), kv[0]))
        lifts = []
        for exercise_id, rows in ranked[:KEY_LIFTS]:
            values = [e1rm(float(x.weight_kg), x.reps) for x in rows]  # rows are oldest first
            lifts.append(s.KeyLift(exercise_id=exercise_id, exercise_name=rows[0].exercise_name,
                                   first_e1rm_kg=_round(values[0]), best_e1rm_kg=_round(max(values))))
        return lifts

    # ------------------------------------------------------------------ charts
    async def chart(self, user: UserRecord, metric: str, period: str) -> s.ChartSeries:
        date_from, date_to = window(period, today_for(user, self.clock))
        series = {"metric": metric, "period": period}
        if not await self._enough_data(user):
            return s.ChartSeries(status="insufficient_data", points=[], **series)
        points: list[tuple[date, float]] = []
        if metric == "weight":
            points = await self.repo.weighins(user.id, date_from, date_to)
        elif metric == "tonnage":
            per_day: dict[date, float] = defaultdict(float)
            for x in await self.repo.completed_sets(user.id, date_from, date_to):
                per_day[x.performed_on] += float(x.weight_kg) * x.reps
            points = sorted((d, _round(v)) for d, v in per_day.items())
        elif metric == "calories":
            points = sorted((d, _round(v, 1)) for d, v in (await self.repo.daily_calories(
                user.id, date_from, date_to)).items())
        elif metric == "workouts_per_week":
            days = await self.repo.workout_dates(user.id, date_from, date_to)
            points = [(start, float(sum(1 for d in days if start <= d <= end)))
                      for start, end in weeks(date_from, date_to)]
        elif metric == "workout_compliance":
            days = await self.repo.workout_dates(user.id, date_from, date_to)
            for start, end in weeks(date_from, date_to):
                value = await self._training_compliance(user, start, end, days)
                if value is not None:
                    points.append((start, value))
        elif metric == "diet_compliance":
            calories = await self.repo.daily_calories(user.id, date_from, date_to)
            for start, end in weeks(date_from, date_to):
                value = await self._diet_compliance(user, start, end, calories)
                if value is not None:
                    points.append((start, value))
        return s.ChartSeries(status="ok", points=[s.ChartPoint(date=d, value=v) for d, v in points], **series)

    # ------------------------------------------------------------------ goal prediction
    async def goal_prediction(self, user: UserRecord) -> s.GoalPrediction:
        """Section 9: a least-squares line through the weigh-ins of the last 28 days against the target weight."""
        today = today_for(user, self.clock)
        profile = await self.uow.profile.get_profile(user.id)
        target = float(profile.target_weight_kg) if profile and profile.target_weight_kg is not None else None
        window_from = today - timedelta(days=PREDICTION_WINDOW_DAYS - 1)
        weighins = await self.repo.weighins(user.id, today - timedelta(days=PREDICTION_WINDOW_DAYS), today)
        compliance = await self._training_compliance(
            user, window_from, today, await self.repo.workout_dates(user.id, window_from, today))
        result = predict_goal(weighins, target, today, compliance)
        return s.GoalPrediction(
            status=result["status"], estimated_date=result.get("estimated_date"),
            slope_kg_per_week=result.get("slope_kg_per_week"), r2=result.get("r2"), target_weight_kg=target,
            warnings=result.get("warnings", []))
