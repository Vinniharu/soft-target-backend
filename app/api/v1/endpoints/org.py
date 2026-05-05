"""Organisation-owner endpoints.

These routes are scoped implicitly to the caller's own organisation —
no path id is needed because the caller's identity already names the
tenant. Authorization is enforced both by the dep (must be admin or
org_owner) and by the service (same-org check).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    CurrentOrgAdmin,
    get_organisation_service,
    get_report_service,
    get_user_service,
)
from app.schemas.organisation import OrganisationRead
from app.schemas.report import ReportListRead, ReportSummaryRead
from app.schemas.user import (
    OrgUserCreate,
    OrgUserUpdate,
    UserListRead,
    UserRead,
)
from app.services.organisation_service import OrganisationService
from app.services.report_service import ReportService
from app.services.user_service import UserService

router = APIRouter(prefix="/org", tags=["org"])


@router.get("/me", response_model=OrganisationRead)
async def get_own_organisation(
    current: CurrentOrgAdmin,
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> OrganisationRead:
    """Return the organisation the caller belongs to. Admins without an
    organisation get 404 — they should use ``/admin/organisations``."""

    org = await service.get_for_caller(actor=current)
    return OrganisationRead.model_validate(org)


# ------------------------------------------------------------------
# Users in own org
# ------------------------------------------------------------------


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_member(
    payload: OrgUserCreate,
    current: CurrentOrgAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.create_user_in_org(payload=payload, actor=current)
    return UserRead.model_validate(user)


@router.get("/users", response_model=UserListRead)
async def list_members(
    current: CurrentOrgAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListRead:
    if current.organisation_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="caller has no organisation",
        )
    users, total = await service.list_users_for_org(
        organisation_id=current.organisation_id,
        actor=current,
        limit=limit,
        offset=offset,
    )
    return UserListRead(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
    )


@router.get("/users/{user_id}", response_model=UserRead)
async def get_member(
    user_id: uuid.UUID,
    current: CurrentOrgAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.get_user_in_org(user_id=user_id, actor=current)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_member(
    user_id: uuid.UUID,
    payload: OrgUserUpdate,
    current: CurrentOrgAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.update_user_in_org(
        user_id=user_id, payload=payload, actor=current
    )
    return UserRead.model_validate(user)


@router.delete(
    "/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_member(
    user_id: uuid.UUID,
    current: CurrentOrgAdmin,
    service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    await service.delete_user_in_org(user_id=user_id, actor=current)


# ------------------------------------------------------------------
# Reports in own org
# ------------------------------------------------------------------


@router.get("/reports", response_model=ReportListRead)
async def list_org_reports(
    current: CurrentOrgAdmin,
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportListRead:
    if current.organisation_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="caller has no organisation",
        )
    reports, total = await service.list_for_org(
        organisation_id=current.organisation_id,
        actor=current,
        limit=limit,
        offset=offset,
    )
    return ReportListRead(
        items=[ReportSummaryRead.model_validate(r) for r in reports],
        total=total,
    )
