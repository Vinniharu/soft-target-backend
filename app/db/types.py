"""Shared column type aliases.

This module exists so models can ``from app.db.types import UUIDPk`` and
get a consistent UUID primary-key column without repeating the same
``mapped_column(...)`` call in every model.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


__all__ = ["JSONB", "UUID", "uuid_pk"]
