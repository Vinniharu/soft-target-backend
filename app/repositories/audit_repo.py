"""Audit log data access."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        count_stmt = select(func.count()).select_from(AuditLog)
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)
