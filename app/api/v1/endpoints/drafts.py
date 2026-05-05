"""Per-user draft endpoints (multi-draft).

Each authenticated user can keep up to ten drafts in flight. Drafts are
strictly per-user — even within an organisation, owners and members
do not see each other's drafts. Cross-user access by id returns ``404``
to avoid leaking the existence of someone else's draft.

Promotion to a real report stays client-driven: read draft → ``POST
/reports`` → ``DELETE /reports/drafts/{id}``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, get_draft_service
from app.schemas.draft import (
    DraftCreate,
    DraftListRead,
    DraftRead,
    DraftSummary,
    DraftUpdate,
)
from app.services.draft_service import DraftService

router = APIRouter(prefix="/reports/drafts", tags=["drafts"])


@router.get("", response_model=DraftListRead)
async def list_drafts(
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DraftListRead:
    drafts, total = await service.list(
        actor=current_user, limit=limit, offset=offset
    )
    return DraftListRead(
        items=[DraftSummary.model_validate(d) for d in drafts],
        total=total,
    )


@router.post(
    "", response_model=DraftRead, status_code=status.HTTP_201_CREATED
)
async def create_draft(
    payload: DraftCreate,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    draft = await service.create(actor=current_user, payload=payload)
    return DraftRead.model_validate(draft)


@router.put("", response_model=DraftRead)
async def upsert_active_draft(
    payload: DraftUpdate,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    """Singleton autosave shortcut.

    Replaces the caller's most-recently-updated draft, or creates one
    if they have none. Same body shape as ``PUT /reports/drafts/{id}``
    (``title`` and ``payload`` both optional). Multi-draft frontends
    that track ids should use the ``/{id}`` form instead.
    """

    draft = await service.upsert_active(actor=current_user, payload=payload)
    return DraftRead.model_validate(draft)


@router.get("/{draft_id}", response_model=DraftRead)
async def get_draft(
    draft_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    draft = await service.get(draft_id=draft_id, actor=current_user)
    return DraftRead.model_validate(draft)


@router.put("/{draft_id}", response_model=DraftRead)
async def update_draft(
    draft_id: uuid.UUID,
    payload: DraftUpdate,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftRead:
    draft = await service.update(
        draft_id=draft_id, actor=current_user, payload=payload
    )
    return DraftRead.model_validate(draft)


@router.delete(
    "/{draft_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_draft(
    draft_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> None:
    await service.delete(draft_id=draft_id, actor=current_user)
