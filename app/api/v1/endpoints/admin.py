"""Admin-only endpoints — user management, organisation management,
audit log access, and admin-scoped report writes (edit/delete)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CurrentAdmin,
    get_audit_repo,
    get_organisation_service,
    get_report_service,
    get_user_service,
)
from app.api.v1.endpoints.reports import _to_read as _report_to_read
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit import AuditEntryRead, AuditListRead
from app.schemas.organisation import (
    OrganisationCreate,
    OrganisationListRead,
    OrganisationRead,
    OrganisationUpdate,
)
from app.schemas.report import (
    ReportListRead,
    ReportRead,
    ReportSummaryRead,
    ReportUpdate,
)
from app.schemas.user import UserCreate, UserListRead, UserRead, UserUpdate
from app.services.organisation_service import OrganisationService
from app.services.report_service import ReportService
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------------------------------------
# Organisations
# ------------------------------------------------------------------


@router.post(
    "/organisations",
    response_model=OrganisationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_organisation(
    payload: OrganisationCreate,
    current_admin: CurrentAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> OrganisationRead:
    org, _owner = await service.create_with_owner(
        payload=payload, actor=current_admin
    )
    return OrganisationRead.model_validate(org)


@router.get("/organisations", response_model=OrganisationListRead)
async def list_organisations(
    current_admin: CurrentAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: Annotated[bool, Query()] = False,
) -> OrganisationListRead:
    orgs, total = await service.list(
        actor=current_admin,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    return OrganisationListRead(
        items=[OrganisationRead.model_validate(o) for o in orgs],
        total=total,
    )


@router.get("/organisations/{org_id}", response_model=OrganisationRead)
async def get_organisation(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> OrganisationRead:
    org = await service.get(org_id, actor=current_admin)
    return OrganisationRead.model_validate(org)


@router.patch("/organisations/{org_id}", response_model=OrganisationRead)
async def update_organisation(
    org_id: uuid.UUID,
    payload: OrganisationUpdate,
    current_admin: CurrentAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> OrganisationRead:
    org = await service.update(
        org_id=org_id, payload=payload, actor=current_admin
    )
    return OrganisationRead.model_validate(org)


@router.delete(
    "/organisations/{org_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_organisation(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> None:
    await service.soft_delete(org_id=org_id, actor=current_admin)


@router.post(
    "/organisations/{org_id}/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_in_org(
    org_id: uuid.UUID,
    payload: UserCreate,
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    # Force the organisation_id from the path; ignore any value in the body.
    payload = payload.model_copy(update={"organisation_id": org_id})
    user = await service.create_user(payload=payload, actor=current_admin)
    return UserRead.model_validate(user)


@router.get(
    "/organisations/{org_id}/users", response_model=UserListRead
)
async def list_users_in_org(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListRead:
    users, total = await service.list_users_for_org(
        organisation_id=org_id,
        actor=current_admin,
        limit=limit,
        offset=offset,
    )
    return UserListRead(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
    )


@router.get(
    "/organisations/{org_id}/reports", response_model=ReportListRead
)
async def list_reports_in_org(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportListRead:
    reports, total = await service.list_for_org(
        organisation_id=org_id,
        actor=current_admin,
        limit=limit,
        offset=offset,
    )
    return ReportListRead(
        items=[ReportSummaryRead.model_validate(r) for r in reports],
        total=total,
    )


# ------------------------------------------------------------------
# Users (flat)
# ------------------------------------------------------------------


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreate,
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.create_user(payload=payload, actor=current_admin)
    return UserRead.model_validate(user)


@router.get("/users", response_model=UserListRead)
async def list_users(
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    organisation_id: Annotated[uuid.UUID | None, Query()] = None,
) -> UserListRead:
    users, total = await service.list_users(
        actor=current_admin,
        limit=limit,
        offset=offset,
        organisation_id=organisation_id,
    )
    return UserListRead(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
    )


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.update_user(
        user_id=user_id, payload=payload, actor=current_admin
    )
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    await service.delete_user(user_id=user_id, actor=current_admin)


# ------------------------------------------------------------------
# Audit & report cross-org writes
# ------------------------------------------------------------------


@router.get("/audit", response_model=AuditListRead)
async def list_audit(
    current_admin: CurrentAdmin,  # noqa: ARG001 — enforces admin role
    audit: Annotated[AuditRepository, Depends(get_audit_repo)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditListRead:
    rows, total = await audit.list_recent(limit=limit, offset=offset)
    return AuditListRead(
        items=[AuditEntryRead.model_validate(r) for r in rows],
        total=total,
    )


@router.patch("/reports/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: uuid.UUID,
    payload: ReportUpdate,
    current_admin: CurrentAdmin,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ReportRead:
    report = await service.update(
        report_id=report_id, payload=payload, actor=current_admin
    )
    return _report_to_read(report)


@router.delete(
    "/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_report(
    report_id: uuid.UUID,
    current_admin: CurrentAdmin,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> None:
    await service.soft_delete(report_id=report_id, actor=current_admin)
