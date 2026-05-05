"""User and authentication business logic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import cache

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)


@cache
def _dummy_password_hash() -> str:
    """Pre-computed bcrypt hash used to keep the email-miss path on the
    same latency budget as the email-hit path. The plaintext is unknown
    to the caller path; this is purely a timing decoy."""

    return hash_password("dummy-password-for-timing-equalization")
from app.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import TokenPair
from app.schemas.user import OrgUserCreate, OrgUserUpdate, UserCreate, UserUpdate
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
            # Run bcrypt against a dummy hash so the email-miss path
            # takes the same time as the email-hit path. Without this,
            # request latency leaks whether an account exists.
            verify_password(password, _dummy_password_hash())
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
            role=user.role,
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

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_role_assignable(actor: User | None, target_role: UserRole) -> None:
        """Block role escalation. Only admins may assign ``admin`` or
        ``org_owner``. Org owners may only assign ``user``. The CLI
        path (``actor is None``) is allowed to assign anything since
        bootstrap requires it."""

        if actor is None or actor.is_admin:
            return
        if target_role != UserRole.user:
            raise PermissionDenied(
                "you may only create or assign the 'user' role"
            )

    async def create_user(
        self, *, payload: UserCreate, actor: User | None
    ) -> User:
        """Admin path. ``actor=None`` is the CLI bootstrap path."""

        if actor is not None and not actor.is_admin:
            raise PermissionDenied("only admins may create users via this path")
        self._assert_role_assignable(actor, payload.role)
        try:
            user = await self._users.create(
                email=payload.email,
                password_hash=hash_password(payload.password),
                name=payload.name,
                role=payload.role,
                organisation_id=payload.organisation_id,
            )
        except ConflictError as exc:
            raise Conflict("email already registered") from exc

        await self._audit.record(
            actor_id=actor.id if actor else None,
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            details={
                "role": payload.role.value,
                "organisation_id": (
                    str(payload.organisation_id)
                    if payload.organisation_id
                    else None
                ),
            },
        )
        return user

    async def create_user_in_org(
        self, *, payload: OrgUserCreate, actor: User
    ) -> User:
        """Org-owner path. Forces ``role=user`` and the actor's own org."""

        if not actor.is_org_owner or actor.organisation_id is None:
            raise PermissionDenied(
                "only organisation owners may create users in their org"
            )
        try:
            user = await self._users.create(
                email=payload.email,
                password_hash=hash_password(payload.password),
                name=payload.name,
                role=UserRole.user,
                organisation_id=actor.organisation_id,
            )
        except ConflictError as exc:
            raise Conflict("email already registered") from exc

        await self._audit.record(
            actor_id=actor.id,
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            details={
                "role": UserRole.user.value,
                "organisation_id": str(actor.organisation_id),
                "via": "org_owner",
            },
        )
        return user

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        payload: UserUpdate,
        actor: User,
    ) -> User:
        """Admin path: edit any user. Also used for admin self-edits."""

        if not actor.is_admin:
            raise PermissionDenied("only admins may edit users via this path")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc

        if payload.role is not None:
            self._assert_role_assignable(actor, payload.role)

        if payload.email is not None:
            user.email = payload.email
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
            await self._refresh_tokens.revoke_all_for_user(user.id)
        if payload.name is not None:
            user.name = payload.name
        if payload.role is not None:
            user.role = payload.role
        if payload.organisation_id is not None:
            user.organisation_id = payload.organisation_id

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
                "name_changed": payload.name is not None,
                "role_changed": payload.role is not None,
                "organisation_changed": payload.organisation_id is not None,
            },
        )
        return user

    async def update_user_in_org(
        self,
        *,
        user_id: uuid.UUID,
        payload: OrgUserUpdate,
        actor: User,
    ) -> User:
        """Org-owner path: edit a member of own org (or self).

        Cannot change role or organisation. The owner may edit themselves
        and any member of their org.
        """

        if not actor.is_org_owner or actor.organisation_id is None:
            raise PermissionDenied("only organisation owners may use this path")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc

        same_org = user.organisation_id == actor.organisation_id
        is_self = user.id == actor.id
        if not same_org and not is_self:
            raise PermissionDenied("user is not in your organisation")

        if payload.email is not None:
            user.email = payload.email
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
            await self._refresh_tokens.revoke_all_for_user(user.id)
        if payload.name is not None:
            user.name = payload.name

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
                "name_changed": payload.name is not None,
                "via": "org_owner",
            },
        )
        return user

    async def delete_user(self, *, user_id: uuid.UUID, actor: User) -> None:
        """Admin path: delete any user. Cannot self-delete. Cannot
        delete an org owner whose organisation is still active —
        delete the organisation first."""

        if not actor.is_admin:
            raise PermissionDenied("only admins may delete users via this path")
        if user_id == actor.id:
            raise PermissionDenied("cannot delete your own account")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc
        if user.is_org_owner and user.organisation_id is not None:
            raise Conflict(
                "this user owns an organisation; "
                "delete the organisation before deleting the owner"
            )
        await self._users.soft_delete(user)
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._audit.record(
            actor_id=actor.id,
            action="user.delete",
            resource_type="user",
            resource_id=str(user.id),
            details={},
        )

    async def delete_user_in_org(
        self, *, user_id: uuid.UUID, actor: User
    ) -> None:
        """Org-owner path: soft-delete a member of own org. Cannot
        delete self, cannot delete the owner (would orphan the org)."""

        if not actor.is_org_owner or actor.organisation_id is None:
            raise PermissionDenied("only organisation owners may use this path")
        if user_id == actor.id:
            raise PermissionDenied("cannot delete your own account")
        try:
            user = await self._users.get(user_id)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc
        if user.organisation_id != actor.organisation_id:
            raise PermissionDenied("user is not in your organisation")
        if user.is_org_owner:
            # Defensive: an org_owner shouldn't share an org with another
            # org_owner, but block the path explicitly.
            raise PermissionDenied("cannot delete the organisation owner")

        await self._users.soft_delete(user)
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._audit.record(
            actor_id=actor.id,
            action="user.delete",
            resource_type="user",
            resource_id=str(user.id),
            details={"via": "org_owner"},
        )

    async def get_user_in_org(
        self, *, user_id: uuid.UUID, actor: User
    ) -> User:
        """Org-owner read of a member (or self) in own org."""

        if not actor.is_org_owner or actor.organisation_id is None:
            raise PermissionDenied("only organisation owners may use this path")
        try:
            user = await self._users.get(user_id, with_organisation=True)
        except NotFoundError as exc:
            raise NotFound("user not found") from exc
        if user.organisation_id != actor.organisation_id and user.id != actor.id:
            raise PermissionDenied("user is not in your organisation")
        return user

    async def list_users(
        self,
        *,
        actor: User,
        limit: int,
        offset: int,
        organisation_id: uuid.UUID | None = None,
    ) -> tuple[list[User], int]:
        if not actor.is_admin:
            raise PermissionDenied("only admins may list users via this path")
        return await self._users.list_active(
            limit=limit, offset=offset, organisation_id=organisation_id
        )

    async def list_users_for_org(
        self,
        *,
        organisation_id: uuid.UUID,
        actor: User,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        """Read-side for both admin (any org) and org_owner (own org only).
        Endpoints choose which dep gates this; the service still
        cross-checks."""

        if actor.is_admin:
            return await self._users.list_for_org(
                organisation_id=organisation_id, limit=limit, offset=offset
            )
        if actor.is_org_owner and actor.organisation_id == organisation_id:
            return await self._users.list_for_org(
                organisation_id=organisation_id, limit=limit, offset=offset
            )
        raise PermissionDenied("not allowed to list users in this organisation")

    async def ensure_admin_seed(
        self, *, email: str, password: str, name: str
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
            name=name,
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
