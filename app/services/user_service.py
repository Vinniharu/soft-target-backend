"""User and authentication business logic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import TokenPair
from app.schemas.user import UserCreate, UserUpdate
from app.services.errors import (
    Conflict,
    InvalidCredentials,
    NotFound,
    PermissionDenied,
)


class UserService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        audit: AuditRepository,
        settings: Settings,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._audit = audit
        self._settings = settings

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidCredentials("invalid email or password")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("invalid email or password")
        return user

    async def issue_tokens(self, user: User) -> TokenPair:
        access_token, claims = create_access_token(
            self._settings, subject=user.id, role=user.role.value
        )
        refresh_token = generate_refresh_token()
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            ttl_days=self._settings.refresh_token_ttl_days,
        )
        ttl_seconds = int((claims.exp - datetime.now(UTC)).total_seconds())
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=max(ttl_seconds, 0),
        )

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        candidates: list[tuple[uuid.UUID, User]] = []
        # Refresh tokens are opaque; we don't know the owner, so we check
        # each active token. In practice the table stays small because
        # rotation marks used_at aggressively — but if it grows, add a
        # lookup column (first 8 chars of token hash, etc.).
        all_users, _ = await self._users.list_active(limit=10000, offset=0)
        for user in all_users:
            rows = await self._refresh_tokens.list_active_for_user(user.id)
            for row in rows:
                if verify_refresh_token(refresh_token, row.token_hash):
                    candidates.append((row.id, user))
                    break
            if candidates:
                break

        if not candidates:
            raise InvalidCredentials("invalid refresh token")

        token_id, user = candidates[0]
        await self._refresh_tokens.mark_used(token_id)
        return await self.issue_tokens(user)

    async def create_user(
        self, *, payload: UserCreate, actor: User | None
    ) -> User:
        if actor is not None and not actor.is_admin:
            raise PermissionDenied("only admins may create users")
        try:
            user = await self._users.create(
                email=payload.email,
                password_hash=hash_password(payload.password),
                role=payload.role,
            )
        except ConflictError as exc:
            raise Conflict("email already registered") from exc

        await self._audit.record(
            actor_id=actor.id if actor else None,
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            details={"role": payload.role.value},
        )
        return user

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        payload: UserUpdate,
        actor: User,
    ) -> User:
        if not actor.is_admin:
            raise PermissionDenied("only admins may edit users")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc

        if payload.email is not None:
            user.email = payload.email
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
            await self._refresh_tokens.revoke_all_for_user(user.id)
        if payload.role is not None:
            user.role = payload.role

        try:
            user = await self._users.update(user)
        except ConflictError as exc:
            raise Conflict("email already registered") from exc

        await self._audit.record(
            actor_id=actor.id,
            action="user.update",
            resource_type="user",
            resource_id=str(user.id),
            details={
                "email_changed": payload.email is not None,
                "password_changed": payload.password is not None,
                "role_changed": payload.role is not None,
            },
        )
        return user

    async def delete_user(self, *, user_id: uuid.UUID, actor: User) -> None:
        if not actor.is_admin:
            raise PermissionDenied("only admins may delete users")
        if user_id == actor.id:
            raise PermissionDenied("cannot delete your own account")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc
        await self._users.soft_delete(user)
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._audit.record(
            actor_id=actor.id,
            action="user.delete",
            resource_type="user",
            resource_id=str(user.id),
            details={},
        )

    async def list_users(
        self, *, actor: User, limit: int, offset: int
    ) -> tuple[list[User], int]:
        if not actor.is_admin:
            raise PermissionDenied("only admins may list users")
        return await self._users.list_active(limit=limit, offset=offset)

    async def ensure_admin_seed(
        self, *, email: str, password: str
    ) -> tuple[User, bool]:
        """Idempotently create the first admin. Used by the CLI.

        Returns the user and a boolean indicating whether a new row was
        inserted.
        """

        existing = await self._users.get_by_email(email, include_deleted=True)
        if existing is not None:
            return existing, False
        user = await self._users.create(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.admin,
        )
        await self._audit.record(
            actor_id=None,
            action="user.seed_admin",
            resource_type="user",
            resource_id=str(user.id),
            details={},
        )
        return user, True
