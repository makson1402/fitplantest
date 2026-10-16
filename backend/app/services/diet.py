"""Diet plan generation and lifecycle (B-12; FR-P4, FR-P5, FR-P6, FR-P7). Rules: docs/algorithms.md section 5."""
from __future__ import annotations

from datetime import timedelta

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.constants import PLAN_DURATION_DAYS
from app.domain.diet import InsufficientFoods, generate_diet
from app.domain.nutrition import nutrition_targets
from app.repositories import UnitOfWork, UserRecord
from app.repositories.diet import DietPlanRecord, NewMeal, NewMealItem
from app.schemas import diet as s
from app.schemas.training import AcceptPlanRequest
from app.services.library import food_summary
from app.services.training import GOAL_NAMES, today_for

# Order of the items inside a meal: the main item first, then side items, fat last (algorithms.md 5.3).
_ROLE_ORDER = {"protein": 0, "dairy": 0, "dish": 0, "carb": 1, "vegetable": 2, "fruit": 3, "fat": 4, "other": 5}


def plan_name(goal: str, diet_type: str, meals_per_day: int) -> str:
    kind = "" if diet_type == "omnivore" else f" ({diet_type})"
    return f"{GOAL_NAMES[goal]} diet{kind}, {meals_per_day} meals per day"


def serialize(plan: DietPlanRecord) -> s.DietPlan:
    return s.DietPlan(
        id=plan.id, name=plan.name, goal=plan.goal, diet_type=plan.diet_type, meals_per_day=plan.meals_per_day,
        status=plan.status, daily_calorie_target=plan.daily_calorie_target,
        protein_target_g=float(plan.protein_target_g), fat_target_g=float(plan.fat_target_g),
        carbs_target_g=float(plan.carbs_target_g), dietary_restrictions=plan.dietary_restrictions,
        generated_at=plan.generated_at, start_date=plan.start_date, end_date=plan.end_date,
        meals=[s.PlannedMeal(
            id=m.id, day_index=m.day_index, meal_type=m.meal_type, meal_order=m.meal_order,
            scheduled_time=m.scheduled_time,
            planned=s.Macros(kcal=float(m.planned_calories), protein=float(m.planned_protein_g),
                             fat=float(m.planned_fat_g), carbs=float(m.planned_carbs_g)),
            items=[s.PlannedMealItem(food=food_summary(i.food), grams=float(i.grams))
                   for i in sorted(m.items, key=lambda i: (_ROLE_ORDER.get(i.food.role, 9), i.food.id))])
            for m in plan.meals])


def insufficient(exc: InsufficientFoods) -> AppError:
    """422 `insufficient_foods`: the roles no eligible food can fill, or the day whose targets cannot be met."""
    details: list[dict] = [{"field": "food", "code": "no_eligible_food", "meal_type": r["meal_type"],
                            "role": r["role"], "message": f"No eligible food for {r['role']} at {r['meal_type']}"}
                           for r in exc.missing_roles]
    if not details:
        details.append({"code": "targets_not_reachable", "message": str(exc)})
    return AppError(422, "insufficient_foods", "Not enough suitable foods for this plan", details)


class DietPlanService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock

    async def generate(self, user: UserRecord, body: s.GenerateDietPlanRequest) -> s.DietPlan:
        """Create the draft diet plan for the profile's goal, replacing an existing draft (nothing changes on 422)."""
        profile = await self.uow.profile.get_profile(user.id)
        if profile is None:
            raise not_found("Profile not found")  # onboarding first
        diet_type = body.diet_type or "omnivore"
        restrictions = body.dietary_restrictions or ""
        targets = nutrition_targets(profile.sex, float(profile.weight_kg), profile.height_cm, profile.age,
                                    float(profile.activity_level_pal), profile.goal)

        await self.uow.training.lock_user(user.id)  # one lock per user for both plan kinds
        foods = await self.uow.library.domain_foods()
        allergens = {a.id for a in await self.uow.profile.user_allergens(user.id)}
        excluded = {f.id for f in await self.uow.profile.excluded_foods(user.id)}
        try:
            plan = generate_diet(targets, body.meals_per_day, foods, diet_type, allergens, excluded)
        except InsufficientFoods as exc:
            raise insufficient(exc) from exc

        order: dict[int, int] = {}
        meals = []
        for m in plan.meals:
            order[m.day_index] = order.get(m.day_index, 0) + 1
            meals.append(NewMeal(
                day_index=m.day_index, meal_type=m.meal_type, meal_order=order[m.day_index],
                calories=round(m.totals.kcal, 2), protein_g=round(m.totals.protein, 2), fat_g=round(m.totals.fat, 2),
                carbs_g=round(m.totals.carbs, 2),
                items=[NewMealItem(i.food_id, i.grams) for i in m.items]))
        await self.uow.diet.delete_draft(user.id)
        plan_id = await self.uow.diet.create_plan(
            user.id, name=plan_name(profile.goal, diet_type, body.meals_per_day), goal=profile.goal,
            diet_type=diet_type, meals_per_day=body.meals_per_day, daily_calorie_target=targets.target_kcal,
            protein_target_g=targets.protein_g, fat_target_g=targets.fat_g, carbs_target_g=targets.carbs_g,
            dietary_restrictions=restrictions, meals=meals)
        await self.uow.commit()
        return serialize(await self.uow.diet.get_plan(user.id, plan_id))  # type: ignore[arg-type]

    async def get_by_status(self, user: UserRecord, status: str) -> s.DietPlan:
        plan = await self.uow.diet.get_plan_by_status(user.id, status)
        if plan is None:
            raise not_found("No such plan")
        return serialize(plan)

    async def accept(self, user: UserRecord, plan_id: int, body: AcceptPlanRequest | None) -> s.DietPlan:
        """The draft becomes active, the previous active diet plan is archived (FR-P7)."""
        await self.uow.training.lock_user(user.id)
        plan = await self.uow.diet.get_plan(user.id, plan_id)
        if plan is None:
            raise not_found("Plan not found")
        if plan.status != "draft":
            raise AppError(409, "conflict", f"Only a draft plan can be accepted (this plan is {plan.status})")
        start = (body.start_date if body and body.start_date else None) or today_for(user, self.clock)
        await self.uow.diet.archive_active(user.id)
        await self.uow.diet.activate(user.id, plan_id, start, start + timedelta(days=PLAN_DURATION_DAYS))
        await self.uow.commit()
        return serialize(await self.uow.diet.get_plan(user.id, plan_id))  # type: ignore[arg-type]
