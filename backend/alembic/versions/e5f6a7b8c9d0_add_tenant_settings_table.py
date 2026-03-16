"""add tenant_settings table for per-tenant labeling config

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-24 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "labeling_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "labeling_confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.75"),
        ),
        sa.Column(
            "label_status",
            sa.String(255),
            nullable=False,
            server_default="JobTracker/Status",
        ),
        sa.Column(
            "label_recruiter",
            sa.String(255),
            nullable=False,
            server_default="JobTracker/Recruiter",
        ),
        sa.Column(
            "label_alerts",
            sa.String(255),
            nullable=False,
            server_default="JobTracker/Alerts",
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_settings_tenant"),
    )


def downgrade() -> None:
    op.drop_table("tenant_settings")
