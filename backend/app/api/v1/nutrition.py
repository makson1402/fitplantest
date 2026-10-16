"""Nutrition routes (B-10). Contract: docs/api/openapi.yaml, tag `diet`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, UowDep
from app.schemas.common import Error
from app.schemas.nutrition import NutritionTargets
from app.services.nutrition import NutritionService

router = APIRouter(tags=["diet"])


def get_nutrition_service(uow: UowDep) -> NutritionService:
    return NutritionService(uow)


@router.get("/nutrition/targets", operation_id="getNutritionTargets",
            summary="BMR, TDEE and macro targets for the current profile", response_model=NutritionTargets,
            responses={401: {"model": Error, "description": "Missing, invalid or expired credentials"},
                       404: {"model": Error, "description": "Not found (no profile yet)"}})
async def get_nutrition_targets(user: CurrentUser,
                                service: Annotated[NutritionService, Depends(get_nutrition_service)]
                                ) -> NutritionTargets:
    return await service.targets(user)
