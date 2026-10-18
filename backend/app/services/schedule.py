"""Reminders, push tokens and the notification inbox (B-14; FR-P9, FR-R7). Design: docs/tasks.md D-08.

Reminders are *local* notifications: the server stores the schedule, the app schedules them on the device from the
answer. `time_of_day` is the wall-clock time of the user and is stored as given, so changing the account's time zone
never shifts a reminder (the clock of the device decides when it rings).
"""
from __future__ import annotations

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.repositories import UnitOfWork, UserRecord
from app.repositories.schedule import ReminderRecord
from app.schemas import schedule as s

MAX_REMINDERS = 50
MAX_DEVICES = 10  # push tokens kept per user; the least recently seen ones are dropped


def _reminder(r: ReminderRecord) -> s.Reminder:
    return s.Reminder(id=r.id, type=r.type, meal_type=r.meal_type, weekdays=r.weekdays, time_of_day=r.time_of_day,
                      message=r.message, is_enabled=r.is_enabled)


class ScheduleService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.repo = uow.schedule

    async def reminders(self, user: UserRecord) -> list[s.Reminder]:
        return [_reminder(r) for r in await self.repo.list_reminders(user.id)]

    async def put_reminders(self, user: UserRecord, body: s.PutRemindersRequest) -> list[s.Reminder]:
        if len(body.reminders) > MAX_REMINDERS:
            raise AppError(422, "validation_error", "Invalid input", [
                {"field": "reminders", "code": "too_long", "message": f"At most {MAX_REMINDERS} reminders"}])
        await self.uow.training.lock_user(user.id)  # two concurrent replacements must not interleave
        saved = await self.repo.replace_reminders(user.id, [r.model_dump() for r in body.reminders])
        await self.uow.commit()
        return [_reminder(r) for r in saved]

    async def register_token(self, user: UserRecord, body: s.PushTokenRequest) -> s.PushToken:
        record = await self.repo.upsert_push_token(user.id, body.token, body.platform, self.clock.now())
        await self.repo.prune_push_tokens(user.id, MAX_DEVICES)
        await self.uow.commit()
        return s.PushToken(id=record.id, token=record.token, platform=record.platform)

    async def delete_token(self, user: UserRecord, token_id: int) -> None:
        if not await self.repo.delete_push_token(user.id, token_id):
            raise not_found("Device not found")
        await self.uow.commit()

    async def notifications(self, user: UserRecord, limit: int, offset: int) -> s.NotificationPage:
        records, total = await self.repo.list_notifications(user.id, limit, offset)
        return s.NotificationPage(
            items=[s.Notification(id=n.id, type=n.type, title=n.title, message=n.message, data=n.data,
                                  created_at=n.created_at, read_at=n.read_at) for n in records],
            total=total, limit=limit, offset=offset)

    async def mark_read(self, user: UserRecord, notification_id: int) -> None:
        if not await self.repo.mark_notification_read(user.id, notification_id, self.clock.now()):
            raise not_found("Notification not found")
        await self.uow.commit()
