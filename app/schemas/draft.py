"""Draft request/response DTOs.

A draft is a free-form JSON blob with an optional title. The server
caps the serialized JSON at 256 KB and the title at 200 chars; nothing
else about the payload is validated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class DraftUpdate(BaseModel):
    """Replace the title and/or the payload of an existing draft.

    A ``null`` payload leaves the stored payload unchanged. Pass an
    empty dict (``{}``) to clear it. The same logic applies to title:
    omit (or send ``null``) to keep, send a new string to replace.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    payload: dict[str, Any] | None = None


class DraftSummary(BaseModel):
    """List-view shape — no payload to keep responses small."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class DraftRead(DraftSummary):
    payload: dict[str, Any]


class DraftListRead(BaseModel):
    items: list[DraftSummary]
    total: int
