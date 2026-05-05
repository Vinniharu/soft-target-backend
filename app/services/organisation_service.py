"""Organisation business logic and authorization.

Owns the "create org and its owner atomically" flow, plus org list/get/
update/soft-delete with the cascade rules: when an org is soft-deleted
its members' refresh tokens are revoked so they can't refresh into a
deactivated tenant. Access tokens for members get rejected at the next
request via the org-active check in :func:`app.api.deps.get_current_user`.
"""

from __future__ import annotations

import uuid

from app.core.security import hash_password
from app.models.organisation import Organisation
from app.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories.organisation_repo import OrganisationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.organisation import OrganisationCreate, OrganisationUpdate
from app.services.errors import (
    Conflict,
    NotFound,
    PermissionDenied,
)


class OrganisationService:
    def __init__(
        self,
        *,
        organisations: OrganisationRepository,
        users: UserRepository,
        audit: AuditRepository,
    ) -> None:
        self._organisations = organisations
        self._users = users
        self._audit = audit

    async def create_with_owner(
        self, *, payload: OrganisationCreate, actor: User
    ) -> tuple[Organisation, User]:
        if not actor.is_admin:
            raise PermissionDenied("only admins may create organisations")

        # Two-step: create the owner user, then the org pointing at them.
        # If the org insert fails (name conflict), the surrounding session
        # transaction rolls back the orphaned user too.
        try:
            owner = await self._users.create(
                email=payload.owner.email,
                password_hash=hash_password(payload.owner.password),
                name=payload.owner.name,
                role=UserRole.org_owner,
                organisation_id=None,
            )
        except ConflictError as exc:
            raise Conflict("owner email already registered") from exc

        try:
            org = await self._organisations.create(
                name=payload.name, owner_user_id=owner.id
            )
        except ConflictError as exc:
            raise Conflict(str(exc)) from exc

        owner.organisation_id = org.id
        await self._users.update(owner)

        await self._audit.record(
            actor_id=actor.id,
            action="organisation.create",
            resource_type="organisation",
            resource_id=str(org.id),
            details={
                "name": org.name,
                "owner_user_id": str(owner.id),
                "owner_email": owner.email,
            },
        )
        return org, owner

    async def get(
        self, org_id: uuid.UUID, *, actor: User
    ) -> Organisation:
        if not actor.is_admin:
            raise PermissionDenied("only admins may view organisations")
        try:
            return await self._organisations.get(org_id, with_owner=True)
        except NotFoundError as exc:
            raise NotFound("organisation not found") from exc

    async def get_for_caller(self, *, actor: User) -> Organisation:
        """Fetch the caller's own organisation. Used by ``/org/me``.

        Admins (who have no organisation) get a 404. Org owners and
        members get their own org back regardless of role.
        """

        if actor.organisation_id is None:
            raise NotFound("caller has no organisation")
        try:
            return await self._organisations.get(
                actor.organisation_id, with_owner=True
            )
        except NotFoundError as exc:
            raise NotFound("organisation not found") from exc

    async def list(
        self, *, actor: User, limit: int, offset: int, include_deleted: bool
    ) -> tuple[list[Organisation], int]:
        if not actor.is_admin:
            raise PermissionDenied("only admins may list organisations")
        return await self._organisations.list_active(
            limit=limit, offset=offset, include_deleted=include_deleted
        )

    async def update(
        self,
        *,
        org_id: uuid.UUID,
        payload: OrganisationUpdate,
        actor: User,
    ) -> Organisation:
        if not actor.is_admin:
            raise PermissionDenied("only admins may edit organisations")
        try:
            org = await self._organisations.get(org_id)
        except NotFoundError as exc:
            raise NotFound("organisation not found") from exc

        if payload.name is not None:
            org.name = payload.name

        try:
            org = await self._organisations.update(org)
        except ConflictError as exc:
            raise Conflict(str(exc)) from exc

        await self._audit.record(
            actor_id=actor.id,
            action="organisation.update",
            resource_type="organisation",
            resource_id=str(org.id),
            details={"name_changed": payload.name is not None},
        )
        return org

    async def soft_delete(self, *, org_id: uuid.UUID, actor: User) -> None:
        if not actor.is_admin:
            raise PermissionDenied("only admins may delete organisations")
        try:
            org = await self._organisations.get(org_id)
        except NotFoundError as exc:
            raise NotFound("organisation not found") from exc

        await self._organisations.soft_delete(org)
        revoked = await self._organisations.revoke_member_tokens(org.id)
        await self._audit.record(
            actor_id=actor.id,
            action="organisation.delete",
            resource_type="organisation",
            resource_id=str(org.id),
            details={"refresh_tokens_revoked": revoked},
        )
