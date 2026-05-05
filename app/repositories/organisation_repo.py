"""Organisation data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organisation import Organisation
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.errors import ConflictError, NotFoundError


class OrganisationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, name: str, owner_user_id: uuid.UUID
    ) -> Organisation:
        org = Organisation(name=name, owner_user_id=owner_user_id)
        self._session.add(org)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "organisation name is already in use, "
                "or the chosen owner already owns another organisation"
            ) from exc
        await self._session.refresh(org)
        return org

    async def get(
        self,
        org_id: uuid.UUID,
        *,
        include_deleted: bool = False,
        with_owner: bool = False,
    ) -> Organisation:
        stmt = select(Organisation).where(Organisation.id == org_id)
        if not include_deleted:
            stmt = stmt.where(Organisation.deleted_at.is_(None))
        if with_owner:
            stmt = stmt.options(selectinload(Organisation.owner))
        result = await self._session.execute(stmt)
        org = result.scalar_one_or_none()
        if org is None:
            raise NotFoundError(f"organisation {org_id} not found")
        return org

    async def update(self, org: Organisation) -> Organisation:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("organisation name is already in use") from exc
        await self._session.refresh(org)
        return org

    async def soft_delete(self, org: Organisation) -> None:
        org.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def list_active(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[Organisation], int]:
        base = select(Organisation)
        if not include_deleted:
            base = base.where(Organisation.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            base.order_by(Organisation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def revoke_member_tokens(self, org_id: uuid.UUID) -> int:
        """Delete refresh tokens for every user in the org. Used when an
        org is soft-deleted so members can't keep refreshing into a
        deactivated tenant."""

        stmt = sql_update(RefreshToken).where(
            RefreshToken.user_id.in_(
                select(User.id).where(User.organisation_id == org_id)
            )
        ).values(used_at=datetime.now(UTC))
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)
