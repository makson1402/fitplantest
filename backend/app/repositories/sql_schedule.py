"""SQLAlchemy implementation of `ScheduleRepository` (B-14)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reports import DevicePushToken, Notification, Reminder
from app.repositories.schedule import NotificationRecord, PushTokenRecord, ReminderRecord


def _reminder(r: Reminder) -> ReminderRecord:
    return ReminderRecord(r.id, r.type, r.meal_type, list(r.weekdays), r.time_of_day, r.message, r.is_enabled)


def _notification(n: Notification) -> NotificationRecord:
    return NotificationRecord(n.id, n.type, n.title, n.message, n.data, n.created_at, n.read_at)


class SqlScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_reminders(self, user_id: int) -> list[ReminderRecord]:
        rows = await self.session.scalars(select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.id)
                                          .execution_options(populate_existing=True))
        return [_reminder(r) for r in rows]

    async def replace_reminders(self, user_id: int, reminders: list[dict]) -> list[ReminderRecord]:
        await self.session.execute(delete(Reminder).where(Reminder.user_id == user_id))
        out = []
        for values in reminders:  # one by one, so that the ids follow the input order
            row = await self.session.scalar(insert(Reminder).values(user_id=user_id, **values).returning(Reminder),
                                            execution_options={"populate_existing": True})
            out.append(_reminder(row))
        return out

    async def upsert_push_token(self, user_id: int, token: str, platform: str, at: datetime) -> PushTokenRecord:
        stmt = pg_insert(DevicePushToken).values(user_id=user_id, token=token, platform=platform, last_seen_at=at)
        stmt = stmt.on_conflict_do_update(index_elements=["token"], set_={
            "user_id": user_id, "platform": platform, "last_seen_at": at}).returning(DevicePushToken)
        row = await self.session.scalar(stmt, execution_options={"populate_existing": True})
        return PushTokenRecord(row.id, row.token, row.platform)

    async def prune_push_tokens(self, user_id: int, keep: int) -> None:
        stale = (select(DevicePushToken.id).where(DevicePushToken.user_id == user_id)
                 .order_by(DevicePushToken.last_seen_at.desc(), DevicePushToken.id.desc()).offset(keep))
        await self.session.execute(delete(DevicePushToken).where(DevicePushToken.id.in_(stale)))

    async def delete_push_token(self, user_id: int, token_id: int) -> bool:
        done = await self.session.scalar(delete(DevicePushToken).where(
            DevicePushToken.id == token_id, DevicePushToken.user_id == user_id).returning(DevicePushToken.id))
        return done is not None

    async def list_notifications(self, user_id: int, limit: int,
                                 offset: int) -> tuple[list[NotificationRecord], int]:
        total = await self.session.scalar(select(func.count()).select_from(Notification)
                                          .where(Notification.user_id == user_id))
        rows = await self.session.scalars(
            select(Notification).where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset)
            .execution_options(populate_existing=True))
        return [_notification(n) for n in rows], int(total or 0)

    async def mark_notification_read(self, user_id: int, notification_id: int, at: datetime) -> bool:
        found = await self.session.scalar(select(Notification.id).where(
            Notification.id == notification_id, Notification.user_id == user_id))
        if found is None:
            return False
        await self.session.execute(update(Notification).where(
            Notification.id == notification_id, Notification.read_at.is_(None)).values(read_at=at))
        return True
