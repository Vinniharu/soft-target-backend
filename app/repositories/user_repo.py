"""User data access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole
from app.repositories.errors import ConflictError, NotFoundError


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        user_id: uuid.UUID,
        *,
        include_deleted: bool = False,
        with_organisation: bool = False,
    ) -> User:
        stmt = select(User).where(User.id == user_id)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        if with_organisation:
            stmt = stmt.options(selectinload(User.organisation))
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"user {user_id} not found")
        return user

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
        with_organisation: bool = False,
    ) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        if with_organisation:
            stmt = stmt.options(selectinload(User.organisation))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        name: str,
        role: UserRole,
        organisation_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            role=role,
            organisation_id=organisation_id,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("email already registered") from exc
        await self._session.refresh(user)
        return user

    async def update(self, user: User) -> User:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("email already registered") from exc
        await self._session.refresh(user)
        return user

    async def soft_delete(self, user: User) -> None:
        from datetime import UTC, datetime

        user.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def list_active(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        organisation_id: uuid.UUID | None = None,
    ) -> tuple[list[User], int]:
        base = select(User).where(User.deleted_at.is_(None))
        if organisation_id is not None:
            base = base.where(User.organisation_id == organisation_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            base.options(selectinload(User.organisation))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def list_for_org(
        self,
        *,
        organisation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        return await self.list_active(
            limit=limit, offset=offset, organisation_id=organisation_id
        )
