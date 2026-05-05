"""Draft ORM model.

A draft is an in-progress report payload that hasn't been promoted to a
real :class:`~app.models.report.Report` yet. Drafts are first-class
rows so a single user can keep several in flight at once. They are
strictly per-user — even within an organisation, owners and members
do not see each other's drafts.

Drafts are not soft-deleted; deletion is a hard ``DELETE``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import JSONB, UUID, uuid_pk

if TYPE_CHECKING:
    from app.models.user import User


class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"
    __table_args__ = (
        Index(
            "ix_drafts_user_id_updated_at",
            "user_id",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    user: Mapped["User"] = relationship(back_populates="drafts")
