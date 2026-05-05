"""drafts table + backfill from users.draft + drop legacy columns

Revision ID: 0005_drafts_table
Revises: 0004_organisations
Create Date: 2026-06-01 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_drafts_table"
down_revision: str | None = "0004_organisations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drafts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_drafts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drafts"),
    )
    op.create_index("ix_drafts_user_id", "drafts", ["user_id"])
    op.create_index(
        "ix_drafts_user_id_updated_at",
        "drafts",
        ["user_id", "updated_at"],
    )

    # Backfill: every non-null users.draft becomes one row in drafts.
    # The created_at/updated_at both fall back to draft_updated_at, or
    # NOW() if that's null.
    op.execute(
        """
        INSERT INTO drafts (id, user_id, title, payload, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            id,
            NULL,
            draft,
            COALESCE(draft_updated_at, NOW()),
            COALESCE(draft_updated_at, NOW())
        FROM users
        WHERE draft IS NOT NULL
        """
    )

    op.drop_column("users", "draft_updated_at")
    op.drop_column("users", "draft")


def downgrade() -> None:
    # Best-effort restore. Re-add the legacy columns and copy back the
    # most-recently-updated draft per user. Any extra drafts beyond the
    # first are dropped — single-draft model only fits one.
    op.add_column(
        "users",
        sa.Column(
            "draft",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "draft_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE users u
        SET
            draft = d.payload,
            draft_updated_at = d.updated_at
        FROM (
            SELECT DISTINCT ON (user_id)
                user_id, payload, updated_at
            FROM drafts
            ORDER BY user_id, updated_at DESC
        ) d
        WHERE u.id = d.user_id
        """
    )

    op.drop_index("ix_drafts_user_id_updated_at", table_name="drafts")
    op.drop_index("ix_drafts_user_id", table_name="drafts")
    op.drop_table("drafts")
