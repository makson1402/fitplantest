"""SQLAlchemy implementation of `NutritionLogRepository` (B-21)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition import DietPlan, Meal, NutritionLog, NutritionLogFoodItem
from app.db.models.reference import FoodItem
from app.repositories.library import FoodRecord
from app.repositories.nutrition_log import (
    DayTotals,
    DietTargets,
    LogItemRecord,
    NewLogItem,
    NutritionLogRecord,
)
from app.repositories.sql_library import _food
from app.repositories.sync import NUTRITION_LOG, SyncPosition
from app.repositories.sync_sql import after


def _log(r: NutritionLog, items: list[LogItemRecord]) -> NutritionLogRecord:
    return NutritionLogRecord(
        id=r.id, user_id=r.user_id, client_uuid=r.client_uuid, log_date=r.log_date, meal_type=r.meal_type,
        meal_photo_url=r.meal_photo_url, actual_calories=r.actual_calories, actual_protein_g=r.actual_protein_g,
        actual_fat_g=r.actual_fat_g, actual_carbs_g=r.actual_carbs_g, hunger_level_before=r.hunger_level_before,
        hunger_level_after=r.hunger_level_after, planned_meal_id=r.planned_meal_id, recognition_id=r.recognition_id,
        logged_at=r.logged_at, updated_at=r.updated_at, deleted_at=r.deleted_at, items=items)


class SqlNutritionLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _items(self, log_ids: list[int]) -> dict[int, list[LogItemRecord]]:
        out: dict[int, list[LogItemRecord]] = {i: [] for i in log_ids}
        if log_ids:
            rows = await self.session.execute(
                select(NutritionLogFoodItem, FoodItem)
                .join(FoodItem, FoodItem.id == NutritionLogFoodItem.food_item_id)
                .where(NutritionLogFoodItem.nutrition_log_id.in_(log_ids))
                .order_by(NutritionLogFoodItem.nutrition_log_id, FoodItem.name, FoodItem.id))
            for item, food in rows:
                out[item.nutrition_log_id].append(LogItemRecord(_food(food), item.grams, item.calories, item.protein_g,
                                                                item.fat_g, item.carbs_g))
        return out

    async def _insert_items(self, log_id: int, items: list[NewLogItem]) -> None:
        if items:
            await self.session.execute(insert(NutritionLogFoodItem), [
                {"nutrition_log_id": log_id, "food_item_id": i.food_item_id, "grams": i.grams,
                 "calories": i.calories, "protein_g": i.protein_g, "fat_g": i.fat_g, "carbs_g": i.carbs_g}
                for i in items])

    async def find_by_client_uuid(self, user_id: int, client_uuid: UUID) -> NutritionLogRecord | None:
        row = await self.session.scalar(select(NutritionLog).where(
            NutritionLog.user_id == user_id, NutritionLog.client_uuid == client_uuid)
            .execution_options(populate_existing=True))
        return _log(row, (await self._items([row.id]))[row.id]) if row else None

    async def active_foods(self, ids: list[int]) -> dict[int, FoodRecord]:
        if not ids:
            return {}
        rows = await self.session.scalars(select(FoodItem).where(FoodItem.id.in_(ids), FoodItem.is_active))
        return {f.id: _food(f) for f in rows}

    async def planned_meal_exists(self, user_id: int, meal_id: int) -> bool:
        found = await self.session.scalar(select(Meal.id).join(DietPlan, DietPlan.id == Meal.diet_plan_id)
                                          .where(Meal.id == meal_id, DietPlan.user_id == user_id))
        return found is not None

    async def create_log(self, user_id: int, values: dict, items: list[NewLogItem]) -> NutritionLogRecord:
        row = await self.session.scalar(insert(NutritionLog).values(user_id=user_id, **values)
                                        .returning(NutritionLog), execution_options={"populate_existing": True})
        await self._insert_items(row.id, items)
        return _log(row, (await self._items([row.id]))[row.id])

    async def get_log(self, user_id: int, log_id: int) -> NutritionLogRecord | None:
        row = await self.session.scalar(select(NutritionLog).where(
            NutritionLog.id == log_id, NutritionLog.user_id == user_id, NutritionLog.deleted_at.is_(None))
            .execution_options(populate_existing=True))
        return _log(row, (await self._items([row.id]))[row.id]) if row else None

    async def list_logs(self, user_id: int, date_from: date | None, date_to: date | None, limit: int,
                        offset: int) -> tuple[list[NutritionLogRecord], int]:
        conditions = [NutritionLog.user_id == user_id, NutritionLog.deleted_at.is_(None)]
        if date_from is not None:
            conditions.append(NutritionLog.log_date >= date_from)
        if date_to is not None:
            conditions.append(NutritionLog.log_date <= date_to)
        total = await self.session.scalar(select(func.count()).select_from(NutritionLog).where(*conditions))
        rows = list(await self.session.scalars(
            select(NutritionLog).where(*conditions).order_by(NutritionLog.log_date.desc(), NutritionLog.id.desc())
            .limit(limit).offset(offset).execution_options(populate_existing=True)))
        items = await self._items([r.id for r in rows])
        return [_log(r, items[r.id]) for r in rows], total or 0

    async def changed_since(self, user_id: int, position: SyncPosition | None,
                            limit: int) -> list[NutritionLogRecord]:
        rows = list(await self.session.scalars(
            select(NutritionLog).where(NutritionLog.user_id == user_id,
                                       after(NutritionLog.updated_at, NutritionLog.id, position, NUTRITION_LOG))
            .order_by(NutritionLog.updated_at, NutritionLog.id).limit(limit)
            .execution_options(populate_existing=True)))
        items = await self._items([r.id for r in rows])
        return [_log(r, items[r.id]) for r in rows]

    async def update_log(self, user_id: int, log_id: int, values: dict,
                         items: list[NewLogItem] | None) -> NutritionLogRecord | None:
        row = await self.session.scalar(
            update(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == user_id,
                                       NutritionLog.deleted_at.is_(None))
            .values(**({"updated_at": func.now()} if not values else values)).returning(NutritionLog),
            execution_options={"populate_existing": True})
        if row is None:
            return None
        if items is not None:
            await self.session.execute(delete(NutritionLogFoodItem).where(
                NutritionLogFoodItem.nutrition_log_id == log_id))
            await self._insert_items(log_id, items)
        return _log(row, (await self._items([log_id]))[log_id])

    async def soft_delete(self, user_id: int, log_id: int, at: datetime) -> bool:
        done = await self.session.scalar(
            update(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == user_id,
                                       NutritionLog.deleted_at.is_(None)).values(deleted_at=at)
            .returning(NutritionLog.id))
        return done is not None

    async def day_totals(self, user_id: int, day: date) -> DayTotals:
        row = (await self.session.execute(
            select(func.count(), func.coalesce(func.sum(NutritionLog.actual_calories), 0),
                   func.coalesce(func.sum(NutritionLog.actual_protein_g), 0),
                   func.coalesce(func.sum(NutritionLog.actual_fat_g), 0),
                   func.coalesce(func.sum(NutritionLog.actual_carbs_g), 0),
                   func.avg(NutritionLog.hunger_level_before), func.avg(NutritionLog.hunger_level_after))
            .where(NutritionLog.user_id == user_id, NutritionLog.log_date == day,
                   NutritionLog.deleted_at.is_(None)))).one()
        count, kcal, protein, fat, carbs, before, after = row
        return DayTotals(count, kcal, protein, fat, carbs, float(before) if before is not None else None,
                         float(after) if after is not None else None)

    async def logged_planned_meal_ids(self, user_id: int, day: date) -> set[int]:
        rows = await self.session.scalars(select(NutritionLog.planned_meal_id).where(
            NutritionLog.user_id == user_id, NutritionLog.log_date == day, NutritionLog.deleted_at.is_(None),
            NutritionLog.planned_meal_id.is_not(None)))
        return set(rows)

    async def active_diet_targets(self, user_id: int) -> DietTargets | None:
        row = await self.session.scalar(select(DietPlan).where(DietPlan.user_id == user_id,
                                                               DietPlan.status == "active")
                                        .execution_options(populate_existing=True))
        if row is None:
            return None
        return DietTargets(row.daily_calorie_target, row.protein_target_g, row.fat_target_g, row.carbs_target_g)
