"""Analytics routes (B-23, B-24). Contract: docs/api/openapi.yaml, tag `analytics`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import analytics as s
from app.schemas.common import Error
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}


def get_service(uow: UowDep, clock: ClockDep) -> AnalyticsService:
    return AnalyticsService(uow, clock)


Service = Annotated[AnalyticsService, Depends(get_service)]
PeriodQuery = Annotated[s.Period, Query()]


@router.get("/summary", operation_id="getAnalyticsSummary", summary="Key metrics for week, month or three months",
            description="Returns status insufficient_data until the history has 7 days with data "
                        "(algorithms.md section 8).",
            response_model=s.AnalyticsSummary, response_model_by_alias=True, responses={**_401, **_422})
async def summary(period: PeriodQuery, user: CurrentUser, service: Service) -> s.AnalyticsSummary:
    return await service.summary(user, period)


@router.get("/charts/{metric}", operation_id="getChartSeries", summary="Time series for a chart",
            response_model=s.ChartSeries, responses={**_401, **_422})
async def chart(metric: Annotated[s.Metric, Path()], period: PeriodQuery, user: CurrentUser,
                service: Service) -> s.ChartSeries:
    return await service.chart(user, metric, period)


@router.get("/goal-prediction", operation_id="getGoalPrediction",
            summary="Estimated date of reaching the target weight", response_model=s.GoalPrediction, responses=_401)
async def goal_prediction(user: CurrentUser, service: Service) -> s.GoalPrediction:
    return await service.goal_prediction(user)
