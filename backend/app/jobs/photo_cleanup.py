"""Expired-photo cleanup (B-26; docs/database/mongo_buffer.md "Photo storage and cleanup").

Deletes photo files under `<PHOTO_DIR>/meals/` that are older than the buffer TTL (6 h) and that nothing refers to:
neither a live MongoDB document (`photoPath`) nor a confirmed recognition (`recognition_ai.image_url`). The MongoDB TTL
index removes documents but cannot remove the files.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from pymongo.asynchronous.database import AsyncDatabase

from app.core.clock import Clock
from app.repositories import UnitOfWorkFactory
from app.repositories.recognitions import DEFAULT_TTL, MongoRecognitionRepository

log = logging.getLogger(__name__)


def delete_unreferenced(photo_dir: str, referenced: set[str], cutoff_timestamp: float) -> int:
    """Blocking file work (run it in a thread). Returns the number of deleted files."""
    root = Path(photo_dir).resolve()
    meals = root / "meals"
    if not meals.is_dir():
        return 0
    kept = {Path(p).as_posix() for p in referenced}
    deleted = 0
    for file in sorted(meals.rglob("*")):
        if not file.is_file() or file.is_symlink():
            continue
        relative = file.resolve().relative_to(root).as_posix()
        if relative in kept or file.stat().st_mtime > cutoff_timestamp:
            continue
        file.unlink(missing_ok=True)
        deleted += 1
    for folder in sorted((d for d in meals.rglob("*") if d.is_dir()), reverse=True):  # empty user folders
        try:
            folder.rmdir()
        except OSError:
            pass  # not empty
    return deleted


async def cleanup_photos(photo_dir: str | None, uow_factory: UnitOfWorkFactory, mongo_db: AsyncDatabase | None,
                         clock: Clock, *, ttl: timedelta = DEFAULT_TTL) -> int:
    if not photo_dir:
        return 0
    if mongo_db is None:  # without the buffer we cannot tell which photos are still in use: delete nothing
        log.warning("photo cleanup skipped: MongoDB is not configured")
        return 0
    now = clock.now()
    referenced = await MongoRecognitionRepository(mongo_db).referenced_photo_paths(now)
    async with uow_factory() as uow:
        referenced |= await uow.jobs.confirmed_photo_paths()
    cutoff = (now - ttl).timestamp()
    deleted = await asyncio.to_thread(delete_unreferenced, photo_dir, referenced, cutoff)
    if deleted:
        log.info("photo cleanup removed %d file(s)", deleted)
    return deleted
