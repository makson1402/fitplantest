"""Declarative base and PostgreSQL enum types shared by all models (mirrors schema_postgres.sql)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Annotated

from sqlalchemy import BigInteger, Date, Identity, Integer, Text, Time, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    # The schema uses text (not varchar) and timestamptz everywhere.
    type_annotation_map = {
        str: Text,
        datetime: TIMESTAMP(timezone=True),
        date: Date,
        time: Time,
        uuid.UUID: UUID(as_uuid=True),
        dict: JSONB,
    }


def pg_enum(name: str, *values: str) -> ENUM:
    # create_type=False: the types are created by the migration, never implicitly by SQLAlchemy.
    return ENUM(*values, name=name, create_type=False)


sex_t = pg_enum("sex_t", "male", "female", "other")
goal_t = pg_enum("goal_t", "weight_loss", "muscle_gain", "strength", "maintenance", "general_fitness", "endurance")
experience_level_t = pg_enum("experience_level_t", "beginner", "intermediate", "advanced")
equipment_t = pg_enum("equipment_t", "none", "home", "gym")
severity_t = pg_enum("severity_t", "mild", "moderate", "severe")
meal_type_t = pg_enum("meal_type_t", "breakfast", "lunch", "dinner", "snack")
weekday_t = pg_enum("weekday_t", "mon", "tue", "wed", "thu", "fri", "sat", "sun")
notification_type_t = pg_enum(
    "notification_type_t", "meal_reminder", "training_reminder", "progress_update", "achievement", "motivational"
)
report_type_t = pg_enum("report_type_t", "weekly", "monthly", "custom")
oauth_provider_t = pg_enum("oauth_provider_t", "google", "apple")
plan_status_t = pg_enum("plan_status_t", "draft", "active", "archived")
adjustment_reason_t = pg_enum(
    "adjustment_reason_t", "baseline", "reduce_high_rpe", "reduce_incomplete_set", "progression"
)
diet_type_t = pg_enum("diet_type_t", "omnivore", "vegetarian", "vegan")
food_role_t = pg_enum("food_role_t", "protein", "carb", "fat", "vegetable", "fruit", "dairy", "dish", "other")
body_region_t = pg_enum("body_region_t", "upper", "lower", "core")

# Reusable column types
Timestamptz = TIMESTAMP(timezone=True)
bigint_pk = Annotated[int, mapped_column(BigInteger, Identity(always=True), primary_key=True)]
int_pk = Annotated[int, mapped_column(Integer, Identity(always=True), primary_key=True)]
now_default = text("now()")
created_at_col = Annotated[datetime, mapped_column(Timestamptz, server_default=now_default)]
