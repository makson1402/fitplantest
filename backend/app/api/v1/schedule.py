"""Schedule routes (B-14): reminders, push tokens, notification inbox. Contract: tag `schedule`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import schedule as s
from app.schemas.common import Error
from app.schemas.ids import OffsetQuery, PathId64
from app.services.schedule import ScheduleService

router = APIRouter(tags=["schedule"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_service(uow: UowDep, clock: ClockDep) -> ScheduleService:
    return ScheduleService(uow, clock)


Service = Annotated[ScheduleService, Depends(get_service)]


@router.get("/reminders", operation_id="listReminders", summary="Training-day and meal-time reminders",
            response_model=list[s.Reminder], responses=_401)
async def list_reminders(user: CurrentUser, service: Service) -> list[s.Reminder]:
    return await service.reminders(user)


@router.put("/reminders", operation_id="putReminders",
            summary="Replace all reminders (the app reschedules local notifications from the answer)",
            response_model=list[s.Reminder], responses={**_401, **_422})
async def put_reminders(body: s.PutRemindersRequest, user: CurrentUser, service: Service) -> list[s.Reminder]:
    return await service.put_reminders(user, body)


@router.post("/devices/push-token", operation_id="registerPushToken",
             summary="Register or refresh the Expo push token of this device", status_code=201,
             response_model=s.PushToken, responses={**_401, **_422})
async def register_push_token(body: s.PushTokenRequest, user: CurrentUser, service: Service) -> s.PushToken:
    return await service.register_token(user, body)


@router.delete("/devices/push-token/{id}", operation_id="deletePushToken",
               summary="Unregister a device (also done on logout)", status_code=204, response_class=Response,
               responses={**_401, **_404, **_422})
async def delete_push_token(id: PathId64, user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.delete_token(user, id)
    return Response(status_code=204)


@router.get("/notifications", operation_id="listNotifications", summary="In-app notification inbox",
            response_model=s.NotificationPage, responses={**_401, **_422})
async def list_notifications(user: CurrentUser, service: Service,
                             limit: Annotated[int, Query(ge=1, le=100)] = 20,
                             offset: OffsetQuery = 0) -> s.NotificationPage:
    return await service.notifications(user, limit, offset)


@router.post("/notifications/{id}/read", operation_id="markNotificationRead", summary="Mark a notification as read",
             status_code=204, response_class=Response, responses={**_401, **_404, **_422})
async def mark_notification_read(id: PathId64, user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.mark_read(user, id)
    return Response(status_code=204)
