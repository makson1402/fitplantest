"""User profile, injuries, allergies and food exclusions (FR-U6, FR-U7, FR-P6)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, PrimaryKeyConstraint, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    bigint_pk,
    created_at_col,
    equipment_t,
    experience_level_t,
    goal_t,
    severity_t,
    sex_t,
)


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    age: Mapped[int] = mapped_column(SmallInteger)
    sex: Mapped[str] = mapped_column(sex_t)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    height_cm: Mapped[int] = mapped_column(SmallInteger)
    activity_level_pal: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    goal: Mapped[str] = mapped_column(goal_t)
    target_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    experience_level: Mapped[str] = mapped_column(experience_level_t)
    equipment: Mapped[str] = mapped_column(equipment_t)
    tdee_kcal: Mapped[int | None]
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]


class Injury(Base):
    __tablename__ = "injury"
    __table_args__ = (Index("injury_user_idx", "user_id"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    injury_type_id: Mapped[int] = mapped_column(ForeignKey("injury_type.id"))
    affected_muscle_group_id: Mapped[int] = mapped_column(ForeignKey("muscle_group.id"))
    severity: Mapped[str] = mapped_column(severity_t)
    start_date: Mapped[date]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    notes: Mapped[str | None]
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]


class UserAllergen(Base):
    __tablename__ = "user_allergen"
    __table_args__ = (PrimaryKeyConstraint("user_id", "allergen_id"),)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    allergen_id: Mapped[int] = mapped_column(ForeignKey("allergen.id"))


class UserExcludedFood(Base):
    __tablename__ = "user_excluded_food"
    __table_args__ = (PrimaryKeyConstraint("user_id", "food_item_id"),)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_item.id", ondelete="CASCADE"))
