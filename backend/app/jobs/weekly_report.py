"""Weekly report job (B-26; FR-R7, algorithms.md section 12).

Every user gets a report for the previous Monday-Sunday once their local time has passed Monday 07:00 of the current
week. The job can run as often as you like (the scheduler runs it every 15 minutes): a report that exists is never
created again, and the notification is created in the same transaction as the report, so there is exactly one of
each per user and week. A job that was down on Monday catches up on the next run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.clock import Clock
from app.core.timezones import load_timezone
from app.repositories import UnitOfWorkFactory, UserRecord
from app.services.reports import ReportService

log = logging.getLogger(__name__)

RUN_AT = time(7, 0)
BATCH = 200


@dataclass
class WeeklyStats:
    users: int = 0
    created: int = 0
    failed: int = 0


def report_week(user: UserRecord, now: datetime) -> tuple[date, date]:
    """(Monday, Sunday) of the newest week whose report is due: the previous week once it is Monday 07:00 in the
    user's zone, before that the week before it."""
    zone = load_timezone(user.timezone) or ZoneInfo("UTC")
    local = now.astimezone(zone)
    monday = local.date() - timedelta(days=local.weekday())
    if local < datetime.combine(monday, RUN_AT, tzinfo=zone):
        monday -= timedelta(days=7)
    start = monday - timedelta(days=7)
    return start, start + timedelta(days=6)


async def run_weekly_reports(uow_factory: UnitOfWorkFactory, clock: Clock) -> WeeklyStats:
    stats = WeeklyStats()
    after = 0
    while True:
        async with uow_factory() as uow:
            users = await uow.users.list_active_after(after, BATCH)
        if not users:
            return stats
        after = users[-1].id
        for user in users:
            stats.users += 1
            try:
                if await _report_for(uow_factory, clock, user):
                    stats.created += 1
            except Exception:  # noqa: BLE001  (one broken account must not stop the others)
                stats.failed += 1
                log.exception("weekly report failed for user %s", user.id)


async def _report_for(uow_factory: UnitOfWorkFactory, clock: Clock, user: UserRecord) -> bool:
    now = clock.now().astimezone(UTC)
    start, end = report_week(user, now)
    async with uow_factory() as uow:
        report = await ReportService(uow, clock).create_auto(user, start, end)
        if report is None:
            return False
        await uow.schedule.create_notification(
            user.id, "progress_update", "Your weekly report is ready",
            f"Report for {start.isoformat()} to {end.isoformat()}: {report.training_sessions_completed} workouts.",
            {"report_id": report.id}, clock.now())
        await uow.commit()
    log.info("weekly report created user=%s report=%s", user.id, report.id)
    return True
