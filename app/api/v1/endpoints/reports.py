"""Report endpoints.

Users can create reports, view their own, and download PDFs. Admin-only
writes (edit, soft-delete) live under ``/admin/reports``. All
authorization lives in :class:`~app.services.report_service.ReportService`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, get_draft_service, get_report_service
from app.schemas.report import (
    DraftRead,
    DraftWrite,
    ReportCreate,
    ReportListRead,
    ReportPayload,
    ReportRead,
    ReportSummaryRead,
)
from app.services.draft_service import DraftService
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_read(report: object) -> ReportRead:
    # Validate the stored JSONB back through the schema so response shape
    # stays consistent regardless of raw storage drift.
    data = ReportPayload.model_validate(report.data)  # type: ignore[attr-defined]
    return ReportRead.model_validate(
        {
            "id": report.id,  # type: ignore[attr-defined]
            "case_id": report.case_id,  # type: ignore[attr-defined]
            "user_id": report.user_id,  # type: ignore[attr-defined]
            "version": report.version,  # type: ignore[attr-defined]
            "created_at": report.created_at,  # type: ignore[attr-defined]
            "updated_at": report.updated_at,  # type: ignore[attr-defined]
            "data": data,
        }
    )


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    current_user: CurrentUser,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ReportRead:
    report = await service.create(payload=payload, creator=current_user)
    return _to_read(report)


@router.get("", response_model=ReportListRead)
async def list_reports(
    current_user: CurrentUser,
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportListRead:
    reports, total = await service.list_for_user(
        actor=current_user, limit=limit, offset=offset
    )
    return ReportListRead(
        items=[ReportSummaryRead.model_validate(r) for r in reports],
        total=total,
    )


@router.get("/draft", response_model=DraftRead)
async def get_draft(
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    payload, updated_at = await service.get(actor=current_user)
    return DraftRead(payload=payload, updated_at=updated_at)


@router.put("/draft", response_model=DraftRead)
async def put_draft(
    payload: DraftWrite,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    saved, updated_at = await service.set(
        actor=current_user, payload=payload.payload
    )
    return DraftRead(payload=saved, updated_at=updated_at)


@router.delete("/draft", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> None:
    await service.clear(actor=current_user)


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ReportRead:
    report = await service.get_for_user(report_id, actor=current_user)
    return _to_read(report)


@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> StreamingResponse:
    report, chunks = await service.stream_pdf(
        report_id=report_id, actor=current_user
    )
    filename = f"{report.case_id}-v{report.version}.pdf"
    return StreamingResponse(
        chunks,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
