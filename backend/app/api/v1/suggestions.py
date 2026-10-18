"""Meal suggestion route (B-22). Contract: docs/api/openapi.yaml, `getMealSuggestions`."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import suggestions as s
from app.schemas.common import Error
from app.services.suggestions import SuggestionService

router = APIRouter(tags=["nutrition"])


def get_service(uow: UowDep, clock: ClockDep) -> SuggestionService:
    return SuggestionService(uow, clock)


@router.get("/nutrition/suggestions", operation_id="getMealSuggestions",
            summary="What to eat now to reach today's targets",
            description="Rules in algorithms.md section 10. Empty list with message target_reached when under 100 kcal "
                        "remain.",
            response_model=s.Suggestions,
            responses={401: {"model": Error, "description": "Missing, invalid or expired credentials"},
                       404: {"model": Error, "description": "No active diet plan"},
                       422: {"model": Error, "description": "Invalid input or a business rule failed"}})
async def get_meal_suggestions(
    user: CurrentUser,
    service: Annotated[SuggestionService, Depends(get_service)],
    date_: Annotated[date | None, Query(alias="date", description="Defaults to today in the user's time zone")] = None,
) -> s.Suggestions:
    return await service.suggestions(user, date_)
