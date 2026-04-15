"""User request/response DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Admin-facing payload to create a new account."""

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.user


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role: UserRole | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class UserListRead(BaseModel):
    items: list[UserRead]
    total: int
