"""Report ORM model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.db.types import JSONB, UUID, uuid_pk

if TYPE_CHECKING:
    from app.models.report_version import ReportVersion
    from app.models.user import User


class Report(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_id_created_at", "user_id", "created_at"),
        Index("ix_reports_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    pdf_path: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    creator: Mapped["User"] = relationship(back_populates="reports")
    versions: Mapped[list["ReportVersion"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReportVersion.edited_at.desc()",
    )
