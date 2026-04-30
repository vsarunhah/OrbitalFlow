"""add ix_jobs_tenant_updated_at for job list ordering

Revision ID: l7m8n9o0p1q2
Revises: k5l6m7n8o9p0
Create Date: 2026-04-14

"""

from alembic import op

revision = "l7m8n9o0p1q2"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_jobs_tenant_updated_at",
        "jobs",
        ["tenant_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_tenant_updated_at", table_name="jobs")
