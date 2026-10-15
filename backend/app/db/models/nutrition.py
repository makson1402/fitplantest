"""Diet plans, meals, photo-recognition results and nutrition logs (FR-P4..P7, FR-A3, FR-N1..N5)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, bigint_pk, created_at_col, diet_type_t, goal_t, meal_type_t, plan_status_t

_UUID_DEFAULT = text("gen_random_uuid()")


class DietPlan(Base):
    __tablename__ = "diet_plan"
    __table_args__ = (
        Index("diet_plan_user_idx", "user_id"),
        Index("diet_plan_one_active", "user_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("diet_plan_one_draft", "user_id", unique=True, postgresql_where=text("status = 'draft'")),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    goal: Mapped[str] = mapped_column(goal_t)
    diet_type: Mapped[str] = mapped_column(diet_type_t, server_default="omnivore")
    meals_per_day: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(plan_status_t, server_default="draft")
    daily_calorie_target: Mapped[int]
    protein_target_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    fat_target_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    carbs_target_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    dietary_restrictions: Mapped[str] = mapped_column(server_default="")
    generated_at: Mapped[created_at_col]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]


class Meal(Base):
    __tablename__ = "meal"
    __table_args__ = (UniqueConstraint("diet_plan_id", "day_index", "meal_order"),)

    id: Mapped[bigint_pk]
    diet_plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("diet_plan.id", ondelete="CASCADE"))
    day_index: Mapped[int] = mapped_column(SmallInteger)
    meal_type: Mapped[str] = mapped_column(meal_type_t)
    meal_order: Mapped[int] = mapped_column(SmallInteger)
    scheduled_time: Mapped[time | None]
    planned_calories: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    planned_protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    planned_fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    planned_carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))


class MealFoodItem(Base):
    __tablename__ = "meal_food_item"
    __table_args__ = (PrimaryKeyConstraint("meal_id", "food_item_id"),)

    meal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meal.id", ondelete="CASCADE"))
    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_item.id"))
    grams: Mapped[Decimal] = mapped_column(Numeric(6, 1))


class RecognitionAI(Base):
    __tablename__ = "recognition_ai"
    __table_args__ = (Index("recognition_ai_user_idx", "user_id"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    image_url: Mapped[str]
    model_name: Mapped[str]
    model_version: Mapped[str | None]
    uploaded_at: Mapped[datetime]
    recognized_items: Mapped[list | dict] = mapped_column(JSONB)
    estimated_calories: Mapped[int]
    estimated_protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    estimated_fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    estimated_carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    was_edited: Mapped[bool]
    created_at: Mapped[created_at_col]


class NutritionLog(Base):
    __tablename__ = "nutrition_log"
    __table_args__ = (
        UniqueConstraint("user_id", "client_uuid"),
        Index("nutrition_log_user_date_idx", "user_id", text("log_date DESC")),
        Index("nutrition_log_user_updated_idx", "user_id", "updated_at"),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    client_uuid: Mapped[uuid.UUID] = mapped_column(server_default=_UUID_DEFAULT)
    log_date: Mapped[date]
    meal_type: Mapped[str] = mapped_column(meal_type_t)
    meal_photo_url: Mapped[str | None]
    actual_calories: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    actual_protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    actual_fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    actual_carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    hunger_level_before: Mapped[int | None] = mapped_column(SmallInteger)
    hunger_level_after: Mapped[int | None] = mapped_column(SmallInteger)
    planned_meal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("meal.id", ondelete="SET NULL"))
    recognition_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("recognition_ai.id", ondelete="SET NULL")
    )
    logged_at: Mapped[created_at_col]
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]
    deleted_at: Mapped[datetime | None]


class NutritionLogFoodItem(Base):
    __tablename__ = "nutrition_log_food_item"
    __table_args__ = (PrimaryKeyConstraint("nutrition_log_id", "food_item_id"),)

    nutrition_log_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nutrition_log.id", ondelete="CASCADE"))
    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_item.id"))
    grams: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    calories: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
