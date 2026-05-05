"""add organisations and tenant columns

Revision ID: 0004_organisations
Revises: 0003_user_draft
Create Date: 2026-05-05 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_organisations"
down_revision: str | None = "0003_user_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_organisations_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organisations"),
    )
    op.create_index(
        "uq_organisations_owner_user_id_active",
        "organisations",
        ["owner_user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_organisations_name_active",
        "organisations",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column(
        "users",
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_users_organisation_id_organisations",
        "users",
        "organisations",
        ["organisation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_users_organisation_id", "users", ["organisation_id"]
    )

    op.add_column(
        "reports",
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_reports_organisation_id_organisations",
        "reports",
        "organisations",
        ["organisation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_reports_organisation_id_created_at",
        "reports",
        ["organisation_id", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reports_organisation_id_created_at", table_name="reports"
    )
    op.drop_constraint(
        "fk_reports_organisation_id_organisations",
        "reports",
        type_="foreignkey",
    )
    op.drop_column("reports", "organisation_id")

    op.drop_index("ix_users_organisation_id", table_name="users")
    op.drop_constraint(
        "fk_users_organisation_id_organisations",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "organisation_id")

    op.drop_index(
        "uq_organisations_name_active", table_name="organisations"
    )
    op.drop_index(
        "uq_organisations_owner_user_id_active", table_name="organisations"
    )
    op.drop_table("organisations")
