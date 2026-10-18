"""Profile, injuries, allergies and excluded foods (B-06). Contract: docs/api/openapi.yaml, tag `account`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, UowDep
from app.schemas import library as lib
from app.schemas import profile as s
from app.schemas.common import Error
from app.schemas.ids import PathId64
from app.services.profile import ProfileService

router = APIRouter(prefix="/users/me", tags=["account"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_profile_service(uow: UowDep) -> ProfileService:
    return ProfileService(uow)


Service = Annotated[ProfileService, Depends(get_profile_service)]
InjuryId = PathId64


@router.get("/profile", operation_id="getProfile", summary="Biometric profile", response_model=s.Profile,
            responses={**_401, **_404})
async def get_profile(user: CurrentUser, service: Service) -> s.Profile:
    return await service.get_profile(user)


@router.put("/profile", operation_id="putProfile", summary="Create or replace the biometric profile",
            description="Validates ranges (algorithms.md section 0) and recomputes TDEE.", response_model=s.Profile,
            responses={**_401, **_422})
async def put_profile(body: s.ProfileInput, user: CurrentUser, service: Service) -> s.Profile:
    return await service.put_profile(user, body)


@router.get("/injuries", operation_id="listInjuries", summary="Injuries and physical limitations",
            response_model=list[s.Injury], responses=_401)
async def list_injuries(user: CurrentUser, service: Service) -> list[s.Injury]:
    return await service.list_injuries(user)


@router.post("/injuries", operation_id="createInjury", summary="Add an injury", status_code=201,
             response_model=s.Injury, responses={**_401, **_422})
async def create_injury(body: s.InjuryInput, user: CurrentUser, service: Service) -> s.Injury:
    return await service.create_injury(user, body)


@router.patch("/injuries/{id}", operation_id="updateInjury", summary="Update an injury (for example mark it healed)",
              response_model=s.Injury, responses={**_401, **_404, **_422})
async def update_injury(id: InjuryId, body: s.InjuryUpdate, user: CurrentUser,  # noqa: A002
                        service: Service) -> s.Injury:
    return await service.update_injury(user, id, body)


@router.delete("/injuries/{id}", operation_id="deleteInjury", summary="Remove an injury", status_code=204,
               response_class=Response, responses={**_401, **_404})
async def delete_injury(id: InjuryId, user: CurrentUser, service: Service) -> Response:  # noqa: A002
    await service.delete_injury(user, id)
    return Response(status_code=204)


@router.get("/allergies", operation_id="getAllergies", summary="The user's allergens and intolerances",
            response_model=list[lib.Allergen], responses=_401)
async def get_allergies(user: CurrentUser, service: Service) -> list[lib.Allergen]:
    return await service.get_allergies(user)


@router.put("/allergies", operation_id="putAllergies", summary="Replace the allergen list",
            response_model=list[lib.Allergen], responses={**_401, **_422})
async def put_allergies(body: s.AllergyList, user: CurrentUser, service: Service) -> list[lib.Allergen]:
    return await service.put_allergies(user, body)


@router.get("/excluded-foods", operation_id="getExcludedFoods", summary="Foods the user never wants in a diet plan",
            response_model=list[lib.FoodSummary], responses=_401)
async def get_excluded_foods(user: CurrentUser, service: Service) -> list[lib.FoodSummary]:
    return await service.get_excluded_foods(user)


@router.put("/excluded-foods", operation_id="putExcludedFoods", summary="Replace the excluded foods",
            response_model=list[lib.FoodSummary], responses={**_401, **_422})
async def put_excluded_foods(body: s.ExcludedFoodList, user: CurrentUser,
                             service: Service) -> list[lib.FoodSummary]:
    return await service.put_excluded_foods(user, body)
