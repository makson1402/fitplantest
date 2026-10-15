"""Reference data (seeded, read-only for the API): muscle groups, injuries, allergens, foods, exercises."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, PrimaryKeyConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    body_region_t,
    equipment_t,
    experience_level_t,
    food_role_t,
    int_pk,
    meal_type_t,
)


class MuscleGroup(Base):
    __tablename__ = "muscle_group"

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(server_default="")
    image_url: Mapped[str | None]
    body_region: Mapped[str] = mapped_column(body_region_t)


class InjuryType(Base):
    __tablename__ = "injury_type"

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(server_default="")
    avg_healing_time_days: Mapped[int] = mapped_column(server_default=text("0"))


class Allergen(Base):
    __tablename__ = "allergen"

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(server_default="")


class FoodCategory(Base):
    __tablename__ = "food_category"

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(server_default="")


class FoodItem(Base):
    __tablename__ = "food_item"

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    calories_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    protein_per_100g: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fat_per_100g: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    carbs_per_100g: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    role: Mapped[str] = mapped_column(food_role_t)
    suitable_meal_types: Mapped[list[str]] = mapped_column(
        ARRAY(meal_type_t), server_default=text("'{breakfast,lunch,dinner,snack}'")
    )
    is_vegetarian: Mapped[bool] = mapped_column(server_default=text("false"))
    is_vegan: Mapped[bool] = mapped_column(server_default=text("false"))
    default_portion_g: Mapped[int] = mapped_column(server_default=text("100"))
    min_portion_g: Mapped[int] = mapped_column(server_default=text("10"))
    max_portion_g: Mapped[int] = mapped_column(server_default=text("400"))
    portion_step_g: Mapped[int] = mapped_column(server_default=text("5"))
    recognition_label: Mapped[str | None] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class FoodCategoryFoodItem(Base):
    __tablename__ = "food_category_food_item"
    __table_args__ = (
        PrimaryKeyConstraint("food_item_id", "food_category_id"),
        Index("food_category_food_item_cat_idx", "food_category_id"),
    )

    food_category_id: Mapped[int] = mapped_column(ForeignKey("food_category.id", ondelete="CASCADE"))
    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_item.id", ondelete="CASCADE"))


class FoodItemAllergen(Base):
    __tablename__ = "food_item_allergen"
    __table_args__ = (
        PrimaryKeyConstraint("food_item_id", "allergen_id"),
        Index("food_item_allergen_allergen_idx", "allergen_id"),
    )

    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_item.id", ondelete="CASCADE"))
    allergen_id: Mapped[int] = mapped_column(ForeignKey("allergen.id", ondelete="CASCADE"))


class Exercise(Base):
    __tablename__ = "exercise"
    __table_args__ = (Index("exercise_main_muscle_idx", "main_muscle_group_id"),)

    id: Mapped[int_pk]
    name: Mapped[str] = mapped_column(unique=True)
    main_muscle_group_id: Mapped[int] = mapped_column(ForeignKey("muscle_group.id"))
    difficulty_level: Mapped[str] = mapped_column(experience_level_t)
    equipment: Mapped[str] = mapped_column(equipment_t)
    is_compound: Mapped[bool] = mapped_column(server_default=text("false"))
    is_bodyweight: Mapped[bool] = mapped_column(server_default=text("false"))
    description: Mapped[str]
    instruction: Mapped[str]


class ExerciseSecondaryMuscleGroup(Base):
    __tablename__ = "exercise_secondary_muscle_group"
    __table_args__ = (PrimaryKeyConstraint("exercise_id", "muscle_group_id"),)

    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id", ondelete="CASCADE"))
    muscle_group_id: Mapped[int] = mapped_column(ForeignKey("muscle_group.id"))


class InjuryTypeExcludedExercise(Base):
    __tablename__ = "injury_type_excluded_exercise"
    __table_args__ = (PrimaryKeyConstraint("injury_type_id", "exercise_id"),)

    injury_type_id: Mapped[int] = mapped_column(ForeignKey("injury_type.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id", ondelete="CASCADE"))
