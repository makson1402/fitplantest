"""Training plans, workout logs, personal records and body metrics (FR-P1..P3, FR-A1..A5, FR-R1)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    adjustment_reason_t,
    bigint_pk,
    created_at_col,
    equipment_t,
    experience_level_t,
    goal_t,
    plan_status_t,
    weekday_t,
)

_UUID_DEFAULT = text("gen_random_uuid()")


class TrainingPlan(Base):
    __tablename__ = "training_plan"
    __table_args__ = (
        Index("training_plan_user_idx", "user_id"),
        Index("training_plan_one_active", "user_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("training_plan_one_draft", "user_id", unique=True, postgresql_where=text("status = 'draft'")),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    goal: Mapped[str] = mapped_column(goal_t)
    num_training_days: Mapped[int] = mapped_column(SmallInteger)
    experience_level: Mapped[str] = mapped_column(experience_level_t)
    equipment: Mapped[str] = mapped_column(equipment_t)
    status: Mapped[str] = mapped_column(plan_status_t, server_default="draft")
    skipped_muscle_group_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default=text("'{}'"))
    generated_at: Mapped[created_at_col]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]


class TrainingSession(Base):
    __tablename__ = "training_session"
    __table_args__ = (
        UniqueConstraint("training_plan_id", "session_order"),
        UniqueConstraint("training_plan_id", "weekday"),
    )

    id: Mapped[bigint_pk]
    training_plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("training_plan.id", ondelete="CASCADE"))
    session_order: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str]
    weekday: Mapped[str] = mapped_column(weekday_t)
    estimated_duration_min: Mapped[int] = mapped_column(SmallInteger)


class SessionExercise(Base):
    __tablename__ = "session_exercise"
    __table_args__ = (
        UniqueConstraint("training_session_id", "position"),
        Index("session_exercise_exercise_idx", "exercise_id"),
    )

    id: Mapped[bigint_pk]
    training_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_session.id", ondelete="CASCADE")
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"))
    original_exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercise.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    planned_sets: Mapped[int] = mapped_column(SmallInteger)
    planned_reps: Mapped[int] = mapped_column(SmallInteger)
    planned_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rest_seconds: Mapped[int] = mapped_column(SmallInteger)


class PlanAdjustment(Base):
    __tablename__ = "plan_adjustment"
    __table_args__ = (Index("plan_adjustment_se_idx", "session_exercise_id"),)

    id: Mapped[bigint_pk]
    session_exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session_exercise.id", ondelete="CASCADE")
    )
    workout_log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workout_log.id", ondelete="SET NULL", name="plan_adjustment_workout_log_fk")
    )
    reason: Mapped[str] = mapped_column(adjustment_reason_t)
    old_sets: Mapped[int | None] = mapped_column(SmallInteger)
    new_sets: Mapped[int | None] = mapped_column(SmallInteger)
    old_reps: Mapped[int | None] = mapped_column(SmallInteger)
    new_reps: Mapped[int | None] = mapped_column(SmallInteger)
    old_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    new_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[created_at_col]


class WorkoutLog(Base):
    __tablename__ = "workout_log"
    __table_args__ = (
        UniqueConstraint("user_id", "client_uuid"),
        Index("workout_log_user_date_idx", "user_id", text("performed_on DESC")),
        Index("workout_log_user_updated_idx", "user_id", "updated_at"),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    client_uuid: Mapped[uuid.UUID] = mapped_column(server_default=_UUID_DEFAULT)
    training_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("training_session.id", ondelete="SET NULL")
    )
    performed_on: Mapped[date]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    overall_rpe: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None]
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]
    deleted_at: Mapped[datetime | None]


class WorkoutSetLog(Base):
    __tablename__ = "workout_set_log"
    __table_args__ = (
        UniqueConstraint("workout_log_id", "exercise_id", "set_number"),
        Index("workout_set_log_exercise_idx", "exercise_id"),
    )

    id: Mapped[bigint_pk]
    workout_log_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workout_log.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"))
    session_exercise_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("session_exercise.id", ondelete="SET NULL")
    )
    set_number: Mapped[int] = mapped_column(SmallInteger)
    reps: Mapped[int] = mapped_column(SmallInteger)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default=text("0"))
    rpe: Mapped[int | None] = mapped_column(SmallInteger)
    completed: Mapped[bool] = mapped_column(server_default=text("true"))


class PersonalRecord(Base):
    __tablename__ = "personal_record"
    __table_args__ = (
        Index(
            "personal_record_one_current", "user_id", "exercise_id", unique=True, postgresql_where=text("is_current")
        ),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"))
    max_weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    max_reps: Mapped[int] = mapped_column(SmallInteger)
    estimated_1rm_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    achieved_on: Mapped[date]
    is_current: Mapped[bool] = mapped_column(server_default=text("true"))
    source_set_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workout_set_log.id", ondelete="SET NULL")
    )


class BodyMetrics(Base):
    __tablename__ = "body_metrics"
    __table_args__ = (
        UniqueConstraint("user_id", "client_uuid"),
        Index(
            "body_metrics_user_day", "user_id", "measured_on", unique=True, postgresql_where=text("deleted_at IS NULL")
        ),
        Index("body_metrics_user_updated_idx", "user_id", "updated_at"),
    )

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    client_uuid: Mapped[uuid.UUID] = mapped_column(server_default=_UUID_DEFAULT)
    measured_on: Mapped[date]
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    chest_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    waist_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    thigh_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bicep_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    hip_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    calf_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    body_fat_percent: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]
    deleted_at: Mapped[datetime | None]
