"""Admin-only endpoints — user management and audit log access."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CurrentAdmin,
    get_audit_repo,
    get_user_service,
)
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit import AuditEntryRead, AuditListRead
from app.schemas.user import UserCreate, UserListRead, UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


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
) -> UserListRead:
    users, total = await service.list_users(
        actor=current_admin, limit=limit, offset=offset
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
