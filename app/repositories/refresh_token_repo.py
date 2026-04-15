"""Refresh token data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.repositories.errors import NotFoundError


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        ttl_days: int,
    ) -> RefreshToken:
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
        row = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RefreshToken]:
        now = datetime.now(UTC)
        stmt = (
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.used_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_used(self, token_id: uuid.UUID) -> None:
        stmt = select(RefreshToken).where(RefreshToken.id == token_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("refresh token not found")
        row.used_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
        await self._session.execute(stmt)
        await self._session.flush()
