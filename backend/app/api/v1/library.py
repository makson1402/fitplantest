"""Reference data and library routes (B-08, B-09). Contract: docs/api/openapi.yaml, tags `reference` and `library`.

All routes need a valid access token (the contract's default security)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, UowDep, get_current_user
from app.schemas import library as s
from app.schemas.common import Error
from app.schemas.ids import Id32, OffsetQuery, PathId32
from app.schemas.library import Equipment, ExperienceLevel, FoodRole
from app.services.library import LibraryService

_auth = [Depends(get_current_user)]
reference = APIRouter(tags=["reference"], dependencies=_auth)
library = APIRouter(tags=["library"], dependencies=_auth)

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found (also used for rows of other users)"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = OffsetQuery


def get_library_service(uow: UowDep) -> LibraryService:
    return LibraryService(uow)


Service = Annotated[LibraryService, Depends(get_library_service)]


# ------------------------------------------------------------------ reference
@reference.get("/injury-types", operation_id="listInjuryTypes", summary="Injury dictionary",
               response_model=list[s.InjuryType], responses=_401)
async def list_injury_types(service: Service) -> list[s.InjuryType]:
    return await service.injury_types()


@reference.get("/allergens", operation_id="listAllergens", summary="Allergen dictionary",
               response_model=list[s.Allergen], responses=_401)
async def list_allergens(service: Service) -> list[s.Allergen]:
    return await service.allergens()


@reference.get("/muscle-groups", operation_id="listMuscleGroups", summary="Muscle groups",
               response_model=list[s.MuscleGroup], responses=_401)
async def list_muscle_groups(service: Service) -> list[s.MuscleGroup]:
    return await service.muscle_groups()


@reference.get("/food-categories", operation_id="listFoodCategories", summary="Food categories",
               response_model=list[s.FoodCategory], responses=_401)
async def list_food_categories(service: Service) -> list[s.FoodCategory]:
    return await service.food_categories()


# ------------------------------------------------------------------ exercises
@library.get("/exercises", operation_id="listExercises", summary="Exercise library", response_model=s.ExercisePage,
             responses={**_401, **_422})
async def list_exercises(
    service: Service,
    q: Annotated[str | None, Query(description="Case-insensitive name search")] = None,
    muscle_group_id: Id32 | None = None,
    equipment: Equipment | None = None,
    difficulty_level: ExperienceLevel | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> s.ExercisePage:
    return await service.list_exercises(q=q, muscle_group_id=muscle_group_id, equipment=equipment,
                                        difficulty_level=difficulty_level, limit=limit, offset=offset)


@library.get("/exercises/{id}", operation_id="getExercise", summary="Exercise with text instructions",
             response_model=s.Exercise, responses={**_401, **_404, **_422})
async def get_exercise(id: PathId32, service: Service) -> s.Exercise:  # noqa: A002
    return await service.get_exercise(id)


@library.get("/exercises/{id}/alternatives", operation_id="listExerciseAlternatives",
             summary="Same-muscle-group alternatives that suit the user", response_model=list[s.ExerciseSummary],
             responses={**_401, **_404, **_422})
async def list_exercise_alternatives(id: PathId32, user: CurrentUser,  # noqa: A002
                                     service: Service) -> list[s.ExerciseSummary]:
    return await service.alternatives(user.id, id)


# ------------------------------------------------------------------ foods
@library.get("/foods", operation_id="listFoods", summary="Food database", response_model=s.FoodPage,
             responses={**_401, **_422})
async def list_foods(
    service: Service,
    q: str | None = None,
    category_id: Id32 | None = None,
    role: FoodRole | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> s.FoodPage:
    return await service.list_foods(q=q, category_id=category_id, role=role, limit=limit, offset=offset)


@library.get("/foods/{id}", operation_id="getFood", summary="Food with nutrition values per 100 g",
             response_model=s.Food, responses={**_401, **_404, **_422})
async def get_food(id: PathId32, service: Service) -> s.Food:  # noqa: A002
    return await service.get_food(id)
