"""Report request/response DTOs.

The payload shape follows the structure described in AGENTS.md:
    - A primary target with IMEI numbers, phone numbers, coordinates
    - A list of soft targets (phone, location, lat/lng)

Validation is strict: extra fields are rejected and the schemas are
reused between services and endpoints but never between request and
response.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.organisation import OrganisationSummary


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PrimaryTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    imei_numbers: list[str] = Field(default_factory=list, max_length=16)
    phone_numbers: list[str] = Field(default_factory=list, max_length=16)
    location: str | None = Field(default=None, max_length=512)
    coordinates: Coordinates | None = None
    notes: str | None = Field(default=None, max_length=8192)


class SoftTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=512)
    coordinates: Coordinates | None = None
    notes: str | None = Field(default=None, max_length=2048)


class ReportPayload(BaseModel):
    """Full report body — stored as JSONB on the row and rendered to PDF."""

    model_config = ConfigDict(extra="forbid")

    primary_target: PrimaryTarget
    soft_targets: list[SoftTarget] = Field(default_factory=list, max_length=64)
    summary: str | None = Field(default=None, max_length=16384)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=64)
    payload: ReportPayload


class ReportUpdate(BaseModel):
    """Edit body. Fields are all optional; missing fields stay as-is.

    Used by both the owner edit (``PATCH /reports/{id}``) and the admin
    cross-user edit (``PATCH /admin/reports/{id}``)."""

    model_config = ConfigDict(extra="forbid")

    case_id: str | None = Field(default=None, min_length=1, max_length=64)
    payload: ReportPayload | None = None


class ReportCreatorRead(BaseModel):
    """Minimal creator block embedded in report responses so admins and
    org owners can tell who sent each report without a separate user
    lookup. ``organisation`` is null for admin-created reports."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    organisation: OrganisationSummary | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: str
    user_id: uuid.UUID
    organisation_id: uuid.UUID | None = None
    creator: ReportCreatorRead
    version: int
    created_at: datetime
    updated_at: datetime
    data: ReportPayload


class ReportSummaryRead(BaseModel):
    """Shape used by list endpoints — omits the full payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: str
    user_id: uuid.UUID
    organisation_id: uuid.UUID | None = None
    creator: ReportCreatorRead
    version: int
    created_at: datetime
    updated_at: datetime


class ReportListRead(BaseModel):
    items: list[ReportSummaryRead]
    total: int


class DraftWrite(BaseModel):
    """Per-user in-progress draft. Free-form JSON body so the frontend can
    save partial form state at any granularity. Server enforces a byte
    cap on the serialized payload."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)


class DraftRead(BaseModel):
    payload: dict[str, Any] | None = None
    updated_at: datetime | None = None
