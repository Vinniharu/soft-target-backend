"""User data access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.repositories.errors import ConflictError, NotFoundError


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID, *, include_deleted: bool = False) -> User:
        stmt = select(User).where(User.id == user_id)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"user {user_id} not found")
        return user

    async def get_by_email(
        self, email: str, *, include_deleted: bool = False
    ) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str, role: UserRole) -> User:
        user = User(email=email, password_hash=password_hash, role=role)
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
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[User], int]:
        count_stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)
