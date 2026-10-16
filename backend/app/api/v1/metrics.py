"""Body measurement routes (B-17). Contract: docs/api/openapi.yaml, tag `workouts`."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import metrics as s
from app.schemas.common import Error
from app.services.metrics import BodyMetricsService

router = APIRouter(prefix="/body-metrics", tags=["workouts"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_409 = {409: {"model": Error, "description": "Conflict"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_service(uow: UowDep, clock: ClockDep) -> BodyMetricsService:
    return BodyMetricsService(uow, clock)


Service = Annotated[BodyMetricsService, Depends(get_service)]


@router.post("", operation_id="saveBodyMetrics",
             summary="Save a measurement (a second save for the same day updates it)",
             response_model=s.BodyMetrics, responses={**_401, **_409, **_422})
async def save(body: s.BodyMetricsInput, user: CurrentUser, service: Service) -> s.BodyMetrics:
    return await service.save(user, body)


@router.get("", operation_id="listBodyMetrics", summary="Measurement history", response_model=list[s.BodyMetrics],
            responses={**_401, **_422})
async def list_body_metrics(user: CurrentUser, service: Service,
                            date_from: Annotated[date | None, Query(alias="from")] = None,
                            date_to: Annotated[date | None, Query(alias="to")] = None) -> list[s.BodyMetrics]:
    return await service.list(user, date_from, date_to)


@router.delete("/{id}", operation_id="deleteBodyMetrics", summary="Delete a measurement", status_code=204,
               response_class=Response, responses={**_401, **_404, **_422})
async def delete(id: Annotated[int, Path(ge=1)], user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.delete(user, id)
    return Response(status_code=204)
