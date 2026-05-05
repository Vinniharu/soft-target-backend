"""Organisation request/response DTOs.

Organisations are the tenant boundary. Every non-admin user belongs to
exactly one organisation; reports are stamped with the creator's
organisation at write time and stay attributed to that org for life.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OwnerSeed(BaseModel):
    """Initial owner credentials supplied with an organisation create.

    The owner is created in the same transaction as the organisation;
    you can't end up with an orphan org.
    """

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner: OwnerSeed


class OrganisationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class OrganisationSummary(BaseModel):
    """Embedded shape used inside user/report responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class OrganisationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class OrganisationListRead(BaseModel):
    items: list[OrganisationRead]
    total: int
