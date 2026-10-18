"""Reminders, push tokens and the notification inbox of one user (B-14)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol


@dataclass
class ReminderRecord:
    id: int
    type: str
    meal_type: str | None
    weekdays: list[str]
    time_of_day: time
    message: str | None
    is_enabled: bool


@dataclass
class PushTokenRecord:
    id: int
    token: str
    platform: str


@dataclass
class NotificationRecord:
    id: int
    type: str
    title: str
    message: str
    data: dict
    created_at: datetime
    read_at: datetime | None


class ScheduleRepository(Protocol):
    async def list_reminders(self, user_id: int) -> list[ReminderRecord]: ...

    async def replace_reminders(self, user_id: int, reminders: list[dict]) -> list[ReminderRecord]:
        """Delete every reminder of the user and insert the given ones (column names as keys); in input order."""
        ...

    async def upsert_push_token(self, user_id: int, token: str, platform: str, at: datetime) -> PushTokenRecord:
        """A token belongs to one device: registering it again (also by another user, after a sign-in on the same
        device) moves it to this user and refreshes `last_seen_at`."""
        ...

    async def prune_push_tokens(self, user_id: int, keep: int) -> None:
        """Keep the `keep` most recently seen tokens of the user."""
        ...

    async def delete_push_token(self, user_id: int, token_id: int) -> bool: ...

    async def list_notifications(self, user_id: int, limit: int,
                                 offset: int) -> tuple[list[NotificationRecord], int]:
        """Newest first, with the total number of notifications of the user."""
        ...

    async def mark_notification_read(self, user_id: int, notification_id: int, at: datetime) -> bool:
        """False when the notification does not exist or belongs to another user. Reading twice keeps the first time."""
        ...
