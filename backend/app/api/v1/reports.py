"""Report routes (B-25). Contract: docs/api/openapi.yaml, tag `analytics`."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import ClockDep, CurrentUser, UowDep
from app.schemas import reports as s
from app.schemas.common import Error
from app.schemas.ids import OffsetQuery, PathId64
from app.services import report_export
from app.services.reports import ReportService, to_schema

router = APIRouter(prefix="/reports", tags=["analytics"])

_401 = {401: {"model": Error, "description": "Missing, invalid or expired credentials"}}
_404 = {404: {"model": Error, "description": "Not found"}}
_422 = {422: {"model": Error, "description": "Invalid input or a business rule failed"}}
_FILE = {200: {"description": "The file", "content": {
    "application/pdf": {"schema": {"type": "string", "format": "binary"}},
    "text/csv": {"schema": {"type": "string", "format": "binary"}}}}}


def get_service(uow: UowDep, clock: ClockDep) -> ReportService:
    return ReportService(uow, clock)


Service = Annotated[ReportService, Depends(get_service)]


@router.get("", operation_id="listReports", summary="Generated reports", response_model=s.ReportPage,
            responses={**_401, **_422})
async def list_reports(
    user: CurrentUser,
    service: Service,
    report_type: Annotated[s.ReportType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: OffsetQuery = 0,
) -> s.ReportPage:
    return await service.list(user, report_type, limit, offset)


@router.post("", operation_id="createReport", summary="Generate a report for a chosen period", status_code=201,
             description="Weekly = Monday-Sunday, monthly = a whole calendar month, otherwise custom. Generating the "
                         "same period again replaces the stored report. Answers 422 `insufficient_data` until the "
                         "history has 7 days with records (algorithms.md section 8).",
             response_model=s.Report, responses={**_401, **_422})
async def create_report(body: s.CreateReportRequest, user: CurrentUser, service: Service) -> s.Report:
    return await service.create(user, body)


@router.get("/{id}", operation_id="getReport", summary="One report", response_model=s.Report,
            responses={**_401, **_404, **_422})
async def get_report(id: PathId64, user: CurrentUser, service: Service) -> s.Report:  # noqa: A002
    return await service.get(user, id)


@router.get("/{id}/export", operation_id="exportReport", summary="Download a report as PDF or CSV",
            response_class=Response, responses={**_FILE, **_401, **_404, **_422})
async def export_report(id: PathId64, format: Annotated[Literal["pdf", "csv"], Query()],  # noqa: A002
                        user: CurrentUser, service: Service) -> Response:
    report = to_schema(await service.record(user, id))
    if format == "pdf":
        content, media_type = report_export.to_pdf(report), "application/pdf"
    else:
        content, media_type = report_export.to_csv(report), "text/csv; charset=utf-8"
    name = f"fitplan-report-{report.period_start.isoformat()}-{report.period_end.isoformat()}.{format}"
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})
