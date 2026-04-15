"""Authentication-related DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class RefreshCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
