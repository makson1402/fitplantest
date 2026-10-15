"""Progress reports, reminders and notifications (FR-R1..R7, FR-P9)."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    bigint_pk,
    created_at_col,
    meal_type_t,
    notification_type_t,
    report_type_t,
    weekday_t,
)


class ProgressReport(Base):
    __tablename__ = "progress_report"
    __table_args__ = (UniqueConstraint("user_id", "report_type", "period_start", "period_end"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    report_type: Mapped[str] = mapped_column(report_type_t)
    period_start: Mapped[date]
    period_end: Mapped[date]
    weight_difference_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    training_volume_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default=text("0"))
    training_sessions_completed: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    training_sessions_planned: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    workout_compliance_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    diet_compliance_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_daily_calories: Mapped[int | None]
    estimated_goal_completion_date: Mapped[date | None]
    irregular_data: Mapped[bool] = mapped_column(server_default=text("false"))
    is_auto: Mapped[bool] = mapped_column(server_default=text("false"))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    generated_at: Mapped[created_at_col]


class Reminder(Base):
    __tablename__ = "reminder"
    __table_args__ = (Index("reminder_user_idx", "user_id"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(notification_type_t)
    meal_type: Mapped[str | None] = mapped_column(meal_type_t)
    weekdays: Mapped[list[str]] = mapped_column(ARRAY(weekday_t))
    time_of_day: Mapped[time]
    message: Mapped[str | None]
    is_enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (Index("notification_user_created_idx", "user_id", text("created_at DESC")),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(notification_type_t)
    title: Mapped[str]
    message: Mapped[str]
    data: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    created_at: Mapped[created_at_col]
    sent_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]


class DevicePushToken(Base):
    __tablename__ = "device_push_token"
    __table_args__ = (Index("device_push_token_user_idx", "user_id"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(unique=True)
    platform: Mapped[str]
    created_at: Mapped[created_at_col]
    last_seen_at: Mapped[created_at_col]
