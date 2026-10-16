"""Nutrition log routes (B-21). Contract: docs/api/openapi.yaml, tag `nutrition`."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import nutrition_log as s
from app.schemas.common import Error
from app.services.nutrition_log import NutritionLogService

router = APIRouter(tags=["nutrition"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_409 = {409: {"model": Error, "description": "Conflict"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_service(uow: UowDep, clock: ClockDep) -> NutritionLogService:
    return NutritionLogService(uow, clock)


Service = Annotated[NutritionLogService, Depends(get_service)]
LogId = Annotated[int, Path(ge=1)]


@router.post("/nutrition-logs", operation_id="createNutritionLog", summary="Log a meal manually or from the plan",
             status_code=201, response_model=s.NutritionLog, responses={**_401, **_409, **_422})
async def create_log(body: s.NutritionLogInput, user: CurrentUser, service: Service) -> s.NutritionLog:
    return await service.create(user, body)


@router.get("/nutrition-logs", operation_id="listNutritionLogs", summary="Logged meals",
            response_model=s.NutritionLogPage, responses={**_401, **_422})
async def list_logs(user: CurrentUser, service: Service,
                    date_from: Annotated[date | None, Query(alias="from")] = None,
                    date_to: Annotated[date | None, Query(alias="to")] = None,
                    limit: Annotated[int, Query(ge=1, le=100)] = 20,
                    offset: Annotated[int, Query(ge=0)] = 0) -> s.NutritionLogPage:
    return await service.list(user, date_from, date_to, limit, offset)


@router.get("/nutrition-logs/{id}", operation_id="getNutritionLog", summary="One logged meal",
            response_model=s.NutritionLog, responses={**_401, **_404, **_422})
async def get_log(id: LogId, user: CurrentUser, service: Service) -> s.NutritionLog:  # noqa: A002
    return await service.get(user, id)


@router.patch("/nutrition-logs/{id}", operation_id="updateNutritionLog", summary="Change items or hunger levels",
              response_model=s.NutritionLog, responses={**_401, **_404, **_422})
async def update_log(id: LogId, body: s.NutritionLogUpdate, user: CurrentUser,  # noqa: A002
                     service: Service) -> s.NutritionLog:
    return await service.update(user, id, body)


@router.delete("/nutrition-logs/{id}", operation_id="deleteNutritionLog", summary="Delete a logged meal (soft delete)",
               status_code=204, response_class=Response, responses={**_401, **_404, **_422})
async def delete_log(id: LogId, user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.delete(user, id)
    return Response(status_code=204)


@router.get("/nutrition/daily-summary", operation_id="getDailySummary",
            summary="Totals of a day against the diet targets", response_model=s.DailySummary,
            responses={**_401, **_422})
async def daily_summary(user: CurrentUser, service: Service,
                        day: Annotated[date, Query(alias="date")]) -> s.DailySummary:
    return await service.daily_summary(user, day)
