"""Workout routes (B-15, B-16). Contract: docs/api/openapi.yaml, tag `workouts`."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import workouts as s
from app.schemas.common import Error
from app.schemas.ids import OffsetQuery, PathId64
from app.services.workouts import WorkoutService

router = APIRouter(tags=["workouts"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_409 = {409: {"model": Error, "description": "Conflict (the client_uuid belongs to a deleted workout)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_workout_service(uow: UowDep, clock: ClockDep) -> WorkoutService:
    return WorkoutService(uow, clock)


Service = Annotated[WorkoutService, Depends(get_workout_service)]
WorkoutId = PathId64


@router.get("/sessions/next", operation_id="getNextSession",
            summary="The next planned session with its current (possibly adapted) values",
            response_model=s.NextSession, responses={**_401, **_404})
async def get_next_session(user: CurrentUser, service: Service) -> s.NextSession:
    return await service.next_session(user)


@router.post("/workouts", operation_id="createWorkout", summary="Save a finished workout and run the adaptation",
             description="Stores the workout with its sets, updates personal records and applies algorithms.md "
                         "section 6. The answer lists the plan adjustments made (empty when there was no explicit "
                         "signal) so the app can tell the user.",
             status_code=201, response_model=s.WorkoutResult, responses={**_401, **_409, **_422})
async def create_workout(body: s.WorkoutInput, user: CurrentUser, service: Service) -> s.WorkoutResult:
    return await service.create(user, body)


@router.get("/workouts", operation_id="listWorkouts", summary="Workout history", response_model=s.WorkoutPage,
            responses={**_401, **_422})
async def list_workouts(
    user: CurrentUser,
    service: Service,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: OffsetQuery = 0,
) -> s.WorkoutPage:
    return await service.list(user, date_from, date_to, limit, offset)


@router.get("/workouts/{id}", operation_id="getWorkout", summary="One workout with its sets",
            response_model=s.Workout, responses={**_401, **_404, **_422})
async def get_workout(id: WorkoutId, user: CurrentUser, service: Service) -> s.Workout:  # noqa: A002
    return await service.get(user, id)


@router.put("/workouts/{id}", operation_id="updateWorkout",
            summary="Replace a saved workout (sets included); does not re-run the adaptation",
            response_model=s.Workout, responses={**_401, **_404, **_422})
async def update_workout(id: WorkoutId, body: s.WorkoutInput, user: CurrentUser,  # noqa: A002
                         service: Service) -> s.Workout:
    return await service.replace(user, id, body)


@router.delete("/workouts/{id}", operation_id="deleteWorkout",
               summary="Delete a workout (soft delete, kept as a tombstone for sync)", status_code=204,
               response_class=Response, responses={**_401, **_404, **_422})
async def delete_workout(id: WorkoutId, user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.delete(user, id)
    return Response(status_code=204)


@router.get("/personal-records", operation_id="listPersonalRecords", summary="Current personal records per exercise",
            response_model=list[s.PersonalRecord], responses=_401)
async def list_personal_records(user: CurrentUser, service: Service) -> list[s.PersonalRecord]:
    return await service.personal_records(user)
