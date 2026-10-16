"""Meal logging and the daily summary (B-21; FR-A3, FR-R2). Macros are computed from the food database, never typed."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.repositories import UnitOfWork, UserRecord
from app.repositories.nutrition_log import NewLogItem, NutritionLogRecord
from app.schemas import diet as diet_schemas
from app.schemas import nutrition_log as s
from app.services.library import food_summary
from app.services.training import today_for

_ONE, _TWO = Decimal("0.1"), Decimal("0.01")
_COLUMN_MAX = Decimal("9999.99")  # numeric(6,2) of the calorie columns


def _part(per100: Decimal, grams: Decimal) -> Decimal:
    """Nutrient amount of `grams` of a food with `per100` per 100 g, rounded half up to 2 places."""
    return (Decimal(per100) * grams / 100).quantize(_TWO, rounding=ROUND_HALF_UP)


def _macros(kcal, protein, fat, carbs) -> diet_schemas.Macros:
    return diet_schemas.Macros(kcal=float(kcal), protein=float(protein), fat=float(fat), carbs=float(carbs))


def serialize(r: NutritionLogRecord) -> s.NutritionLog:
    return s.NutritionLog(
        id=r.id, client_uuid=r.client_uuid, log_date=r.log_date, meal_type=r.meal_type,
        meal_photo_url=r.meal_photo_url,
        items=[s.NutritionLogItem(food=food_summary(i.food), grams=float(i.grams),
                                  nutrition=_macros(i.calories, i.protein_g, i.fat_g, i.carbs_g)) for i in r.items],
        totals=_macros(r.actual_calories, r.actual_protein_g, r.actual_fat_g, r.actual_carbs_g),
        hunger_level_before=r.hunger_level_before, hunger_level_after=r.hunger_level_after,
        planned_meal_id=r.planned_meal_id, recognition_id=r.recognition_id, logged_at=r.logged_at,
        updated_at=r.updated_at)


def _problem(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


class NutritionLogService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.repo = uow.nutrition_log

    async def _items(self, items: list[s.NutritionLogItemInput]) -> tuple[list[NewLogItem], dict]:
        """Items with macros from the food database (per 100 g x grams / 100, rounded half up to 2 places) and the
        totals of the meal, which are exactly the sum of the rounded items."""
        problems: list[dict] = []
        foods = await self.repo.active_foods(sorted({i.food_item_id for i in items}))
        seen: set[int] = set()
        stored: list[NewLogItem] = []
        for index, item in enumerate(items):
            food = foods.get(item.food_item_id)
            if food is None:
                problems.append(_problem(f"items.{index}.food_item_id", "not_found", "Unknown food"))
                continue
            if item.food_item_id in seen:
                problems.append(_problem(f"items.{index}.food_item_id", "duplicate",
                                         "A food can appear once in a meal: add the grams together"))
                continue
            seen.add(item.food_item_id)
            grams = Decimal(str(item.grams)).quantize(_ONE, rounding=ROUND_HALF_UP)
            if grams <= 0:
                problems.append(_problem(f"items.{index}.grams", "out_of_range", "At least 0.1 g"))
                continue
            stored.append(NewLogItem(item.food_item_id, grams, _part(food.calories_per_100g, grams),
                                     _part(food.protein_per_100g, grams), _part(food.fat_per_100g, grams),
                                     _part(food.carbs_per_100g, grams)))
        if not problems and sum(i.calories for i in stored) > _COLUMN_MAX:
            problems.append(_problem("items", "too_large", "A single meal cannot exceed 9999.99 kcal"))
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)
        return stored, {
            "actual_calories": sum(i.calories for i in stored), "actual_protein_g": sum(i.protein_g for i in stored),
            "actual_fat_g": sum(i.fat_g for i in stored), "actual_carbs_g": sum(i.carbs_g for i in stored)}

    async def create(self, user: UserRecord, body: s.NutritionLogInput) -> s.NutritionLog:
        await self.uow.training.lock_user(user.id)
        if body.client_uuid is not None:
            existing = await self.repo.find_by_client_uuid(user.id, body.client_uuid)
            if existing is not None:  # a retry: answer with the log the first request stored
                if existing.deleted_at is not None:
                    raise AppError(409, "conflict", "A log with this client_uuid was deleted")
                return serialize(existing)
        problems = []
        if body.log_date > today_for(user, self.clock) + timedelta(days=1):
            problems.append(_problem("log_date", "future_date", "A meal cannot be logged for the future"))
        if body.planned_meal_id is not None and not await self.repo.planned_meal_exists(user.id, body.planned_meal_id):
            problems.append(_problem("planned_meal_id", "not_found", "Unknown planned meal"))
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)
        items, totals = await self._items(body.items)
        record = await self.repo.create_log(user.id, {
            "client_uuid": body.client_uuid or uuid4(), "log_date": body.log_date, "meal_type": body.meal_type,
            "hunger_level_before": body.hunger_level_before, "hunger_level_after": body.hunger_level_after,
            "planned_meal_id": body.planned_meal_id, **totals}, items)
        await self.uow.commit()
        return serialize(record)

    async def list(self, user: UserRecord, date_from: date | None, date_to: date | None, limit: int,
                   offset: int) -> s.NutritionLogPage:
        records, total = await self.repo.list_logs(user.id, date_from, date_to, limit, offset)
        return s.NutritionLogPage(items=[serialize(r) for r in records], total=total, limit=limit, offset=offset)

    async def get(self, user: UserRecord, log_id: int) -> s.NutritionLog:
        record = await self.repo.get_log(user.id, log_id)
        if record is None:
            raise not_found("Log not found")
        return serialize(record)

    async def update(self, user: UserRecord, log_id: int, body: s.NutritionLogUpdate) -> s.NutritionLog:
        await self.uow.training.lock_user(user.id)
        if await self.repo.get_log(user.id, log_id) is None:
            raise not_found("Log not found")
        sent = body.model_fields_set
        values: dict = {k: getattr(body, k) for k in ("hunger_level_before", "hunger_level_after") if k in sent}
        items = None
        if "items" in sent:
            items, totals = await self._items(body.items)
            values.update(totals)
        record = await self.repo.update_log(user.id, log_id, values, items)
        await self.uow.commit()
        return serialize(record)  # type: ignore[arg-type]

    async def delete(self, user: UserRecord, log_id: int) -> None:
        if not await self.repo.soft_delete(user.id, log_id, self.clock.now()):
            raise not_found("Log not found")
        await self.uow.commit()

    async def daily_summary(self, user: UserRecord, day: date) -> s.DailySummary:
        """Totals of the day's live logs against the targets of the active diet plan (null without one)."""
        totals = await self.repo.day_totals(user.id, day)
        targets = await self.repo.active_diet_targets(user.id)
        spent = _macros(totals.calories, totals.protein_g, totals.fat_g, totals.carbs_g)
        goal = remaining = None
        if targets is not None:
            goal = _macros(targets.calories, targets.protein_g, targets.fat_g, targets.carbs_g)
            remaining = _macros(targets.calories - totals.calories, targets.protein_g - totals.protein_g,
                                targets.fat_g - totals.fat_g, targets.carbs_g - totals.carbs_g)
        def avg(v):
            return round(v, 2) if v is not None else None
        return s.DailySummary(date=day, targets=goal, totals=spent, remaining=remaining, logs_count=totals.logs_count,
                              avg_hunger_before=avg(totals.avg_hunger_before),
                              avg_hunger_after=avg(totals.avg_hunger_after))
