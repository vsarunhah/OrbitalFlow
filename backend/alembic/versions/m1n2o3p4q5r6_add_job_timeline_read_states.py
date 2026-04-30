"""add job_timeline_read_states for per-user new-email tracking

Revision ID: m1n2o3p4q5r6
Revises: l7m8n9o0p1q2
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_timeline_read_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "job_id",
            name="uq_job_timeline_read_tenant_user_job",
        ),
    )
    op.create_index(
        "ix_job_timeline_read_tenant_user",
        "job_timeline_read_states",
        ["tenant_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_timeline_read_tenant_user", table_name="job_timeline_read_states")
    op.drop_table("job_timeline_read_states")
