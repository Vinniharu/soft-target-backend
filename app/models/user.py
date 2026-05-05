"""User account ORM model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.db.types import JSONB, UUID, uuid_pk

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.organisation import Organisation
    from app.models.refresh_token import RefreshToken
    from app.models.report import Report


class UserRole(str, enum.Enum):
    user = "user"
    org_owner = "org_owner"
    admin = "admin"


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=16),
        nullable=False,
        default=UserRole.user,
    )
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    draft_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organisation: Mapped["Organisation | None"] = relationship(
        back_populates="members",
        foreign_keys=[organisation_id],
    )
    owned_organisation: Mapped["Organisation | None"] = relationship(
        back_populates="owner",
        foreign_keys="Organisation.owner_user_id",
        uselist=False,
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="creator",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(
        back_populates="actor",
        passive_deletes=True,
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    @property
    def is_org_owner(self) -> bool:
        return self.role == UserRole.org_owner

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None
