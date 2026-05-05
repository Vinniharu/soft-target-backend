"""User request/response DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.schemas.organisation import OrganisationSummary


class UserCreate(BaseModel):
    """Admin-facing payload to create a new account.

    ``role`` and ``organisation_id`` are admin-only fields. Org owners
    creating users in their own org should use :class:`OrgUserCreate`,
    which omits both (server forces ``role=user`` and the caller's
    organisation).
    """

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    role: UserRole = UserRole.user
    organisation_id: uuid.UUID | None = None


class OrgUserCreate(BaseModel):
    """Org-owner facing payload to create a member in the caller's own
    organisation. The role is forced to ``user`` and the organisation
    is taken from the caller's identity — neither is accepted from the
    request body."""

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    organisation_id: uuid.UUID | None = None


class OrgUserUpdate(BaseModel):
    """Org-owner facing edit. Cannot change role or organisation."""

    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=100)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    organisation: OrganisationSummary | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class UserListRead(BaseModel):
    items: list[UserRead]
    total: int
