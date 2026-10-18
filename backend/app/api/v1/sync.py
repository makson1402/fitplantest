"""Offline sync routes (B-27). Contract: docs/api/openapi.yaml, tag `sync`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import sync as s
from app.schemas.common import Error
from app.services.sync import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_service(uow: UowDep, clock: ClockDep) -> SyncService:
    return SyncService(uow, clock)


Service = Annotated[SyncService, Depends(get_service)]


@router.post("/push", operation_id="syncPush", summary="Upload changes made offline",
             description="Scope: workout logs, nutrition logs, body metrics (design D-07). Idempotent by "
                         "`client_uuid`: "
                         "sending the same item again changes nothing. Optimistic concurrency: when `base_updated_at` "
                         "is given and differs from the stored `updated_at`, the item is not applied and the server "
                         "copy is returned with status `conflict` (server wins; the app replaces its local copy). A "
                         "new item has no `base_updated_at`. Adaptation is not run for synced workouts.",
             response_model=s.SyncPushResponse, responses={**_401, **_422})
async def sync_push(body: s.SyncPushRequest, user: CurrentUser, service: Service) -> s.SyncPushResponse:
    return await service.push(user, body)


@router.get("/pull", operation_id="syncPull", summary="Download changes since a cursor",
            description="Items include tombstones (`deleted_at` set). Without a cursor everything is returned in "
                        "pages. The cursor is opaque; the server applies a small overlap so no change is missed, so "
                        "the client must apply items idempotently.",
            response_model=s.SyncPullResponse, responses={**_401, **_422})
async def sync_pull(user: CurrentUser, service: Service, cursor: Annotated[str | None, Query()] = None,
                    limit: Annotated[int, Query(ge=1, le=500)] = 200) -> s.SyncPullResponse:
    return await service.pull(user, cursor, limit)
