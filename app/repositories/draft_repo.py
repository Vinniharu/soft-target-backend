"""Draft data access."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.repositories.errors import NotFoundError


class DraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        title: str | None,
        payload: dict[str, Any],
    ) -> Draft:
        draft = Draft(user_id=user_id, title=title, payload=payload)
        self._session.add(draft)
        await self._session.flush()
        await self._session.refresh(draft)
        return draft

    async def get(self, draft_id: uuid.UUID) -> Draft:
        stmt = select(Draft).where(Draft.id == draft_id)
        result = await self._session.execute(stmt)
        draft = result.scalar_one_or_none()
        if draft is None:
            raise NotFoundError(f"draft {draft_id} not found")
        return draft

    async def update(self, draft: Draft) -> Draft:
        await self._session.flush()
        await self._session.refresh(draft)
        return draft

    async def delete(self, draft: Draft) -> None:
        await self._session.delete(draft)
        await self._session.flush()

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Draft], int]:
        base = select(Draft).where(Draft.user_id == user_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            base.order_by(Draft.updated_at.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def count_for_user(self, *, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Draft)
            .where(Draft.user_id == user_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def delete_for_user(self, *, user_id: uuid.UUID) -> int:
        """Hard-delete every draft owned by a user. Used (rarely) when an
        admin force-deletes a user — drafts cascade via FK CASCADE in
        prod, but the explicit method exists for tests."""

        stmt = sql_delete(Draft).where(Draft.user_id == user_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)
