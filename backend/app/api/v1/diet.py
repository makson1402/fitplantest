"""Diet plan routes (B-12). Contract: docs/api/openapi.yaml, tag `diet`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import diet as s
from app.schemas.common import Error
from app.schemas.ids import PathId64
from app.schemas.training import AcceptPlanRequest
from app.services.diet import DietPlanService

router = APIRouter(prefix="/diet-plans", tags=["diet"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_409 = {409: {"model": Error, "description": "Conflict (for example plan state)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_diet_service(uow: UowDep, clock: ClockDep) -> DietPlanService:
    return DietPlanService(uow, clock)


Service = Annotated[DietPlanService, Depends(get_diet_service)]


@router.post("/generate", operation_id="generateDietPlan", summary="Generate a draft 7-day diet plan",
             description="422 `insufficient_foods` when the targets cannot be met with the eligible foods "
                         "(algorithms.md 5.5).",
             status_code=201, response_model=s.DietPlan,
             responses={**_401, 404: {"model": Error, "description": "Profile missing"}, **_422})
async def generate(body: s.GenerateDietPlanRequest, user: CurrentUser, service: Service) -> s.DietPlan:
    return await service.generate(user, body)


@router.get("/active", operation_id="getActiveDietPlan", summary="The accepted diet plan",
            response_model=s.DietPlan, responses={**_401, **_404})
async def get_active(user: CurrentUser, service: Service) -> s.DietPlan:
    return await service.get_by_status(user, "active")


@router.get("/draft", operation_id="getDraftDietPlan", summary="The diet plan waiting for acceptance",
            response_model=s.DietPlan, responses={**_401, **_404})
async def get_draft(user: CurrentUser, service: Service) -> s.DietPlan:
    return await service.get_by_status(user, "draft")


@router.post("/{id}/accept", operation_id="acceptDietPlan", summary="Accept the draft diet plan",
             response_model=s.DietPlan, responses={**_401, **_404, **_409, **_422})
async def accept(id: PathId64, user: CurrentUser, service: Service,  # noqa: A002
                 body: Annotated[AcceptPlanRequest, Body()] = None) -> s.DietPlan:  # type: ignore[assignment]
    return await service.accept(user, id, body)
