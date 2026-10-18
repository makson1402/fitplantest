"""Runs the scheduled jobs (B-26): `python -m app.jobs once` runs each job once, `python -m app.jobs loop` repeats them
every `SCHEDULER_INTERVAL_SECONDS` (default 15 minutes). Run ONE scheduler process; every job is idempotent, so a second
one (or a restart) only costs time, never duplicates."""
from __future__ import annotations

import asyncio
import logging
from functools import partial

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.mongo import create_mongo_client
from app.db.session import create_engine_from_url
from app.jobs.dispatch import dispatch_pending
from app.jobs.photo_cleanup import cleanup_photos
from app.jobs.weekly_report import run_weekly_reports
from app.repositories import UnitOfWorkFactory
from app.repositories.sql import sql_uow_factory
from app.services.push import ExpoPushSender, PushSender

log = logging.getLogger(__name__)


async def run_once(settings: Settings, uow_factory: UnitOfWorkFactory, clock: Clock, mongo_db,
                   sender: PushSender | None) -> None:
    """Each job is isolated: a failing one is logged and the others still run."""
    jobs = {
        "weekly_reports": partial(run_weekly_reports, uow_factory, clock),
        "photo_cleanup": partial(cleanup_photos, settings.photo_dir, uow_factory, mongo_db, clock),
    }
    if sender is not None:  # after the reports, so that a fresh notification goes out in the same run
        jobs["push_dispatch"] = partial(dispatch_pending, uow_factory, clock, sender)
    for name, job in jobs.items():
        try:
            log.info("job %s finished: %s", name, await job())
        except Exception:  # noqa: BLE001
            log.exception("job %s failed", name)


async def main(mode: str, settings: Settings | None = None) -> None:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    url = settings.resolved_database_url
    if not url:
        raise SystemExit("persistence is not configured: set DATABASE_URL or POSTGRES_USER/PASSWORD/DB")
    engine = create_engine_from_url(url, pool_size=2, max_overflow=2, pool_timeout=settings.db_pool_timeout_seconds,
                                    pool_recycle=settings.db_pool_recycle_seconds)
    mongo_url = settings.resolved_mongo_url
    mongo_client = create_mongo_client(mongo_url) if mongo_url else None
    mongo_db = mongo_client[settings.mongo_db] if mongo_client else None
    sender = ExpoPushSender(settings.expo_push_url, settings.expo_access_token) if settings.push_enabled else None
    uow_factory, clock = sql_uow_factory(engine), SystemClock()
    try:
        while True:
            await run_once(settings, uow_factory, clock, mongo_db, sender)
            if mode == "once":
                return
            await asyncio.sleep(settings.scheduler_interval_seconds)
    finally:
        if sender is not None:
            await sender.aclose()
        if mongo_client is not None:
            await mongo_client.close()
        await engine.dispose()
