"""Real-time meal suggestions (B-22; FR-N5). Rules: docs/algorithms.md section 10 (app/domain/suggestions).

The service gathers the inputs: the targets of the active diet plan, what the day's logs already hold, the foods the
user may eat (allergens, excluded foods, diet type) and the planned meals of the day that are not logged yet.
"""
from __future__ import annotations

from datetime import date

from app.core.clock import Clock
from app.core.errors import not_found
from app.domain.diet import eligible_foods
from app.domain.meal_scaling import Macros
from app.domain.suggestions import remaining, suggest
from app.repositories import UnitOfWork, UserRecord
from app.schemas import diet as diet_schemas
from app.schemas import suggestions as s
from app.services.library import food_summary
from app.services.training import today_for

PLAN_DAYS = 7


def plan_day_index(start: date | None, day: date) -> int:
    """The plan repeats every 7 days from its start date: day 1 is the start date (algorithms.md 5.3)."""
    return ((day - start).days % PLAN_DAYS) + 1 if start else 1


def _api(m: Macros) -> diet_schemas.Macros:
    return diet_schemas.Macros(kcal=round(m.kcal, 1), protein=round(m.protein, 1), fat=round(m.fat, 1),
                               carbs=round(m.carbs, 1))


class SuggestionService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock

    async def suggestions(self, user: UserRecord, day: date | None) -> s.Suggestions:
        plan = await self.uow.diet.get_plan_by_status(user.id, "active")
        if plan is None:
            raise not_found("No active diet plan")
        day = day or today_for(user, self.clock)
        daily = Macros(float(plan.daily_calorie_target), float(plan.protein_target_g), float(plan.fat_target_g),
                       float(plan.carbs_target_g))
        totals = await self.uow.nutrition_log.day_totals(user.id, day)
        logged = Macros(float(totals.calories), float(totals.protein_g), float(totals.fat_g), float(totals.carbs_g))

        allergens = {a.id for a in await self.uow.profile.user_allergens(user.id)}
        excluded = {f.id for f in await self.uow.profile.excluded_foods(user.id)}
        foods = eligible_foods(await self.uow.library.domain_foods(), None, plan.diet_type, allergens, excluded)
        allowed = {f.id for f in foods}

        # The plan was generated for the allergies of that time: a meal with a food that is not allowed now is dropped.
        eaten = await self.uow.nutrition_log.logged_planned_meal_ids(user.id, day)
        index = plan_day_index(plan.start_date, day)
        planned = [(m.id, Macros(float(m.planned_calories), float(m.planned_protein_g), float(m.planned_fat_g),
                                 float(m.planned_carbs_g)))
                   for m in plan.meals
                   if m.day_index == index and m.id not in eaten and all(i.food.id in allowed for i in m.items)]

        chosen, message = suggest(daily, logged, foods, planned)
        left = remaining(daily, logged)
        foods_by_id = await self.uow.nutrition_log.active_foods([c.ref_id for c in chosen if c.kind == "food"])
        out = [s.Suggestion(
            type=c.kind, food=food_summary(foods_by_id[c.ref_id]) if c.kind == "food" else None,
            grams=float(c.grams) if c.grams is not None else None,
            planned_meal_id=c.ref_id if c.kind == "planned_meal" else None, nutrition=_api(c.macros),
            score=round(c.score, 4)) for c in chosen]
        # Over the target already: nothing is left to eat, the answer shows zeros rather than negative numbers.
        left = Macros(max(left.kcal, 0), max(left.protein, 0), max(left.fat, 0), max(left.carbs, 0))
        return s.Suggestions(remaining=_api(left), message=message, suggestions=out)
