"""Organisation ORM model.

An organisation is the tenant boundary. Every non-admin user belongs to
exactly one organisation; reports are stamped with the creator's
organisation at write time and stay attributed to that org.

A partial unique index on ``owner_user_id`` (where ``deleted_at IS
NULL``) enforces the one-owner-per-org invariant. The owner is also a
regular row in ``users`` with ``role=org_owner``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.db.types import UUID, uuid_pk

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.user import User


class Organisation(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organisations"
    __table_args__ = (
        Index(
            "uq_organisations_owner_user_id_active",
            "owner_user_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index(
            "uq_organisations_name_active",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(
        foreign_keys=[owner_user_id],
        back_populates="owned_organisation",
    )
    members: Mapped[list["User"]] = relationship(
        back_populates="organisation",
        foreign_keys="User.organisation_id",
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="organisation",
    )
