"""Offline sync: push and pull of workouts, nutrition logs and body measurements (B-27; NFR-OFF, design D-07).

Rules
-----
* Items are identified by the `client_uuid` the app generated, so every push is idempotent: sending an item again
  changes nothing (`unchanged`).
* Conflicts: the server wins. When the client edits or deletes an item with a `base_updated_at` that is not the stored
  `updated_at`, nothing is applied and the stored item comes back as `server_copy` with status `conflict`; the app
  replaces its local copy. Workouts and nutrition logs are append-only (D-07): they can be created and deleted, and an
  edit of an existing one is a conflict. Body measurements can be edited (one per day).
* Deletes are tombstones (`deleted_at`); a deleted item stays deleted: re-creating its `client_uuid` is a conflict.
* Every item is its own transaction: a rejected item (validation error) does not affect the others.
* Pull returns the changed items of all three kinds in one stream ordered by (updated_at, kind, id). The cursor is
  the position of the last item of a page; once the client has caught up the cursor is `now - 60 s`, so a change
  that committed late (its `updated_at` is the start time of its transaction) is delivered again rather than
  missed. The client therefore applies pulled items idempotently.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from app.core.clock import Clock
from app.core.errors import AppError, error_body
from app.repositories import UnitOfWork, UserRecord
from app.repositories.sync import BODY_METRICS, NUTRITION_LOG, WORKOUT, SyncPosition
from app.schemas import sync as s
from app.schemas.common import Error
from app.services.metrics import BodyMetricsService
from app.services.metrics import serialize as serialize_metrics
from app.services.nutrition_log import NutritionLogService
from app.services.nutrition_log import serialize as serialize_log
from app.services.workouts import WorkoutService, serialize_workout

log = logging.getLogger(__name__)

OVERLAP = timedelta(seconds=60)
MAX_ITEMS = 200  # items per push; a bigger backlog is sent in several requests

_MEASUREMENTS = ("chest_cm", "waist_cm", "thigh_cm", "bicep_cm", "hip_cm", "calf_cm", "body_fat_percent")


def encode_cursor(position: SyncPosition) -> str:
    raw = json.dumps({"t": position.updated_at.isoformat(), "r": position.rank, "i": position.id},
                     separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(text: str) -> SyncPosition:
    try:
        raw = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        stamp = datetime.fromisoformat(raw["t"])
        rank, id_ = int(raw["r"]), int(raw["i"])
        if stamp.tzinfo is None or rank not in (WORKOUT, NUTRITION_LOG, BODY_METRICS) or not 0 <= id_ < 2**63:
            raise ValueError
        return SyncPosition(stamp, rank, id_)
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise AppError(422, "validation_error", "Invalid input", [
            {"field": "cursor", "code": "invalid", "message": "Not a cursor issued by this server"}]) from None


def _error(exc: AppError) -> Error:
    return Error.model_validate(error_body(exc.code, exc.message, exc.details))


def _workout_out(record) -> s.SyncWorkoutOut:
    return s.SyncWorkoutOut(**serialize_workout(record).model_dump(), deleted_at=record.deleted_at)


def _log_out(record) -> s.SyncNutritionLogOut:
    return s.SyncNutritionLogOut(**serialize_log(record).model_dump(), deleted_at=record.deleted_at)


def _metrics_out(record) -> s.SyncBodyMetricsOut:
    return s.SyncBodyMetricsOut(**serialize_metrics(record).model_dump(), deleted_at=record.deleted_at)


class SyncService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock

    # ------------------------------------------------------------------ results
    @staticmethod
    def _done(kind: str, client_uuid: UUID, status: str, record=None, copy: Any = None) -> s.SyncItemResult:
        return s.SyncItemResult(
            type=kind, client_uuid=client_uuid, status=status, server_id=getattr(record, "id", None),
            server_updated_at=getattr(record, "updated_at", None),
            server_copy=copy.model_dump(mode="json") if copy is not None else None)

    # ------------------------------------------------------------------ push
    async def push(self, user: UserRecord, body: s.SyncPushRequest) -> s.SyncPushResponse:
        workouts, logs, metrics = body.workouts or [], body.nutrition_logs or [], body.body_metrics or []
        if len(workouts) + len(logs) + len(metrics) > MAX_ITEMS:
            raise AppError(422, "validation_error", "Invalid input", [
                {"field": "workouts", "code": "too_long", "message": f"At most {MAX_ITEMS} items per request"}])
        results: list[s.SyncItemResult] = []
        for kind, items, handler in (("workout", workouts, self._workout), ("nutrition_log", logs, self._log),
                                     ("body_metrics", metrics, self._metrics)):
            for item in items:
                results.append(await self._guarded(kind, item.client_uuid, handler, user, item))
        return s.SyncPushResponse(results=results, cursor=self._caught_up_cursor())

    async def _guarded(self, kind: str, client_uuid: UUID, handler, user: UserRecord, item) -> s.SyncItemResult:
        try:
            return await handler(user, item)
        except AppError as exc:
            await self.uow.rollback()
            return s.SyncItemResult(type=kind, client_uuid=client_uuid, status="rejected", error=_error(exc))
        except DBAPIError as exc:  # a value the database cannot store: the client's input, like the REST routes
            sqlstate = str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")
            if not sqlstate.startswith("22"):
                raise
            await self.uow.rollback()
            return s.SyncItemResult(type=kind, client_uuid=client_uuid, status="rejected", error=_error(AppError(
                422, "validation_error", "Invalid input",
                [{"code": "invalid_value", "message": "A value is outside what can be stored"}])))

    @staticmethod
    def _stale(item, record) -> bool:
        """The client edits a version of the item that is not the stored one."""
        return item.base_updated_at is not None and item.base_updated_at != record.updated_at

    async def _workout(self, user: UserRecord, item: s.SyncWorkout) -> s.SyncItemResult:
        service, repo = WorkoutService(self.uow, self.clock), self.uow.workouts
        existing = await repo.find_by_client_uuid(user.id, item.client_uuid)
        if existing is None:
            if item.deleted:
                return self._done("workout", item.client_uuid, "unchanged")
            created = (await service.create(user, item, adapt=False)).workout
            return self._done("workout", item.client_uuid, "applied", created)
        if existing.deleted_at is not None:
            if item.deleted:
                return self._done("workout", item.client_uuid, "unchanged", existing)
            return self._done("workout", item.client_uuid, "conflict", existing, _workout_out(existing))
        if item.deleted:
            if self._stale(item, existing):
                return self._done("workout", item.client_uuid, "conflict", existing, _workout_out(existing))
            await service.delete(user, existing.id)
            return self._done("workout", item.client_uuid, "applied",
                              await repo.find_by_client_uuid(user.id, item.client_uuid))
        # append-only: sending it again is a retry; an edit of a stored workout is not accepted
        if item.base_updated_at is None:
            return self._done("workout", item.client_uuid, "unchanged", existing)
        return self._done("workout", item.client_uuid, "conflict", existing, _workout_out(existing))

    async def _log(self, user: UserRecord, item: s.SyncNutritionLog) -> s.SyncItemResult:
        service, repo = NutritionLogService(self.uow, self.clock), self.uow.nutrition_log
        existing = await repo.find_by_client_uuid(user.id, item.client_uuid)
        if existing is None:
            if item.deleted:
                return self._done("nutrition_log", item.client_uuid, "unchanged")
            created = await service.create(user, item)
            return self._done("nutrition_log", item.client_uuid, "applied", created)
        if existing.deleted_at is not None:
            if item.deleted:
                return self._done("nutrition_log", item.client_uuid, "unchanged", existing)
            return self._done("nutrition_log", item.client_uuid, "conflict", existing, _log_out(existing))
        if item.deleted:
            if self._stale(item, existing):
                return self._done("nutrition_log", item.client_uuid, "conflict", existing, _log_out(existing))
            await service.delete(user, existing.id)
            return self._done("nutrition_log", item.client_uuid, "applied",
                              await repo.find_by_client_uuid(user.id, item.client_uuid))
        if item.base_updated_at is None:
            return self._done("nutrition_log", item.client_uuid, "unchanged", existing)
        return self._done("nutrition_log", item.client_uuid, "conflict", existing, _log_out(existing))

    async def _metrics(self, user: UserRecord, item: s.SyncBodyMetrics) -> s.SyncItemResult:
        service, repo = BodyMetricsService(self.uow, self.clock), self.uow.metrics
        existing = await repo.find_by_client_uuid(user.id, item.client_uuid)

        def conflict(record) -> s.SyncItemResult:
            return self._done("body_metrics", item.client_uuid, "conflict", record, _metrics_out(record))

        if existing is None:
            if item.deleted:
                return self._done("body_metrics", item.client_uuid, "unchanged")
            other = await repo.find_by_day(user.id, item.measured_on)
            if other is not None:  # another device measured the same day first: the server's measurement stands
                return conflict(other)
            saved = await service.save(user, item)
            return self._done("body_metrics", item.client_uuid, "applied", saved)
        if existing.deleted_at is not None:
            if item.deleted:
                return self._done("body_metrics", item.client_uuid, "unchanged", existing)
            return conflict(existing)
        if item.deleted:
            if self._stale(item, existing):
                return conflict(existing)
            await service.delete(user, existing.id)
            return self._done("body_metrics", item.client_uuid, "applied",
                              await repo.find_by_client_uuid(user.id, item.client_uuid))
        values = service._values(user, item)  # noqa: SLF001  (the same validation and rounding as the REST route)
        if all(getattr(existing, name) == value for name, value in values.items()):
            return self._done("body_metrics", item.client_uuid, "unchanged", existing)  # a retry, or no change
        if item.base_updated_at is None or self._stale(item, existing):
            return conflict(existing)
        other = await repo.find_by_day(user.id, item.measured_on)
        if other is not None and other.id != existing.id:
            return conflict(other)
        saved = await service.save(user, item)
        return self._done("body_metrics", item.client_uuid, "applied", saved)

    # ------------------------------------------------------------------ pull
    def _caught_up_cursor(self) -> str:
        return encode_cursor(SyncPosition(self.clock.now() - OVERLAP, 0, 0))

    async def pull(self, user: UserRecord, cursor: str | None, limit: int) -> s.SyncPullResponse:
        position = decode_cursor(cursor) if cursor else None
        found: list[tuple[datetime, int, int, Any]] = []   # one more than a page of each kind is enough to know
        for rank, records in ((WORKOUT, await self.uow.workouts.changed_since(user.id, position, limit + 1)),
                              (NUTRITION_LOG, await self.uow.nutrition_log.changed_since(user.id, position, limit + 1)),
                              (BODY_METRICS, await self.uow.metrics.changed_since(user.id, position, limit + 1))):
            found += [(r.updated_at, rank, r.id, r) for r in records]
        found.sort(key=lambda x: x[:3])
        page, has_more = found[:limit], len(found) > limit
        cursor_out = (encode_cursor(SyncPosition(page[-1][0], page[-1][1], page[-1][2])) if has_more
                      else self._caught_up_cursor())
        return s.SyncPullResponse(
            cursor=cursor_out, has_more=has_more,
            workouts=[_workout_out(r) for _, rank, _, r in page if rank == WORKOUT],
            nutrition_logs=[_log_out(r) for _, rank, _, r in page if rank == NUTRITION_LOG],
            body_metrics=[_metrics_out(r) for _, rank, _, r in page if rank == BODY_METRICS])
