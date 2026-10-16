"""SQLAlchemy implementation of `DietRepository` (B-12)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition import DietPlan, Meal, MealFoodItem
from app.db.models.reference import FoodItem
from app.repositories.diet import DietPlanRecord, MealItemRecord, MealRecord, NewMeal
from app.repositories.sql_library import _food


class SqlDietRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_draft(self, user_id: int) -> None:
        # meals and their foods go with the plan (ON DELETE CASCADE); nutrition logs only lose the link (SET NULL)
        await self.session.execute(delete(DietPlan).where(DietPlan.user_id == user_id, DietPlan.status == "draft"))

    async def create_plan(self, user_id: int, *, name: str, goal: str, diet_type: str, meals_per_day: int,
                          daily_calorie_target: int, protein_target_g: float, fat_target_g: float,
                          carbs_target_g: float, dietary_restrictions: str, meals: list[NewMeal]) -> int:
        plan_id = await self.session.scalar(insert(DietPlan).values(
            user_id=user_id, name=name, goal=goal, diet_type=diet_type, meals_per_day=meals_per_day,
            status="draft", daily_calorie_target=daily_calorie_target, protein_target_g=protein_target_g,
            fat_target_g=fat_target_g, carbs_target_g=carbs_target_g, dietary_restrictions=dietary_restrictions,
        ).returning(DietPlan.id))
        for m in meals:
            meal_id = await self.session.scalar(insert(Meal).values(
                diet_plan_id=plan_id, day_index=m.day_index, meal_type=m.meal_type, meal_order=m.meal_order,
                planned_calories=m.calories, planned_protein_g=m.protein_g, planned_fat_g=m.fat_g,
                planned_carbs_g=m.carbs_g).returning(Meal.id))
            if m.items:
                await self.session.execute(insert(MealFoodItem), [
                    {"meal_id": meal_id, "food_item_id": i.food_item_id, "grams": i.grams} for i in m.items])
        return plan_id

    async def get_plan(self, user_id: int, plan_id: int) -> DietPlanRecord | None:
        return await self._load(DietPlan.id == plan_id, DietPlan.user_id == user_id)

    async def get_plan_by_status(self, user_id: int, status: str) -> DietPlanRecord | None:
        return await self._load(DietPlan.user_id == user_id, DietPlan.status == status)

    async def archive_active(self, user_id: int) -> None:
        await self.session.execute(update(DietPlan).where(
            DietPlan.user_id == user_id, DietPlan.status == "active").values(status="archived"))

    async def activate(self, user_id: int, plan_id: int, start_date: date, end_date: date) -> None:
        await self.session.execute(update(DietPlan).where(
            DietPlan.id == plan_id, DietPlan.user_id == user_id).values(
            status="active", start_date=start_date, end_date=end_date))

    async def _load(self, *conditions) -> DietPlanRecord | None:
        plan = await self.session.scalar(select(DietPlan).where(*conditions).execution_options(populate_existing=True))
        if plan is None:
            return None
        record = DietPlanRecord(
            id=plan.id, user_id=plan.user_id, name=plan.name, goal=plan.goal, diet_type=plan.diet_type,
            meals_per_day=plan.meals_per_day, status=plan.status, daily_calorie_target=plan.daily_calorie_target,
            protein_target_g=plan.protein_target_g, fat_target_g=plan.fat_target_g, carbs_target_g=plan.carbs_target_g,
            dietary_restrictions=plan.dietary_restrictions, generated_at=plan.generated_at,
            start_date=plan.start_date, end_date=plan.end_date)
        meals = {}
        for m in await self.session.scalars(
            select(Meal).where(Meal.diet_plan_id == plan.id).order_by(Meal.day_index, Meal.meal_order)
        ):
            meals[m.id] = MealRecord(m.id, m.day_index, m.meal_type, m.meal_order, m.scheduled_time,
                                     m.planned_calories, m.planned_protein_g, m.planned_fat_g, m.planned_carbs_g)
            record.meals.append(meals[m.id])
        if meals:
            rows = await self.session.execute(
                select(MealFoodItem.meal_id, MealFoodItem.grams, FoodItem)
                .join(FoodItem, FoodItem.id == MealFoodItem.food_item_id)
                .where(MealFoodItem.meal_id.in_(meals)).order_by(MealFoodItem.meal_id, FoodItem.id))
            for meal_id, grams, food in rows:
                meals[meal_id].items.append(MealItemRecord(_food(food), grams))
        return record
