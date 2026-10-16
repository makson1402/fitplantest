"""Training plan routes (B-11). Contract: docs/api/openapi.yaml, tag `training`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import training as s
from app.schemas.common import Error
from app.services.training import TrainingPlanService

router = APIRouter(prefix="/training-plans", tags=["training"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_409 = {409: {"model": Error, "description": "Conflict (for example plan state)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_training_service(uow: UowDep, clock: ClockDep) -> TrainingPlanService:
    return TrainingPlanService(uow, clock)


Service = Annotated[TrainingPlanService, Depends(get_training_service)]


@router.post("/generate", operation_id="generateTrainingPlan", summary="Generate a draft training plan",
             description="Creates (and replaces) the user's draft plan. When a required muscle group has no eligible "
                         "exercise the answer is 422 `insufficient_exercises` with `details` listing the groups and "
                         "the suggestions `change_equipment` / `change_goal` (algorithms.md 4.4). Must answer within "
                         "3 s.",
             status_code=201, response_model=s.TrainingPlan,
             responses={**_401, 404: {"model": Error, "description": "Profile missing"}, **_422})
async def generate(body: s.GenerateTrainingPlanRequest, user: CurrentUser, service: Service) -> s.TrainingPlan:
    return await service.generate(user, body)


@router.get("/active", operation_id="getActiveTrainingPlan", summary="The accepted plan",
            response_model=s.TrainingPlan, responses={**_401, **_404})
async def get_active(user: CurrentUser, service: Service) -> s.TrainingPlan:
    return await service.get_by_status(user, "active")


@router.get("/draft", operation_id="getDraftTrainingPlan", summary="The plan waiting for acceptance",
            response_model=s.TrainingPlan, responses={**_401, **_404})
async def get_draft(user: CurrentUser, service: Service) -> s.TrainingPlan:
    return await service.get_by_status(user, "draft")


@router.post("/{id}/accept", operation_id="acceptTrainingPlan",
             summary="Accept the draft (it becomes active, the previous active plan is archived)",
             response_model=s.TrainingPlan, responses={**_401, **_404, **_409, **_422})
async def accept(id: Annotated[int, Path(ge=1)], user: CurrentUser, service: Service,  # noqa: A002
                 body: Annotated[s.AcceptPlanRequest, Body()] = None) -> s.TrainingPlan:  # type: ignore[assignment]
    return await service.accept(user, id, body)


exercises_router = APIRouter(prefix="/session-exercises", tags=["training"])


@exercises_router.patch("/{id}", operation_id="updateSessionExercise",
                        summary="Edit sets, reps, weight or rest of a planned exercise",
                        response_model=s.SessionExercise, responses={**_401, **_404, **_409, **_422})
async def update_session_exercise(id: Annotated[int, Path(ge=1)], body: s.SessionExerciseUpdate,  # noqa: A002
                                  user: CurrentUser, service: Service) -> s.SessionExercise:
    return await service.update_exercise(user, id, body)


@exercises_router.put("/{id}/swap", operation_id="swapSessionExercise",
                      summary="Replace the exercise with an alternative of the same muscle group",
                      description="Rejects with 422 `invalid_swap` when the exercise is ineligible or from another "
                                  "muscle group.",
                      response_model=s.SessionExercise, responses={**_401, **_404, **_409, **_422})
async def swap_session_exercise(id: Annotated[int, Path(ge=1)], body: s.SwapRequest,  # noqa: A002
                                user: CurrentUser, service: Service) -> s.SessionExercise:
    return await service.swap_exercise(user, id, body)
