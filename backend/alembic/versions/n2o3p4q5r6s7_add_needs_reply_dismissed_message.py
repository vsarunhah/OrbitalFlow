"""add needs_reply_dismissed_up_to_message_id to job_timeline_read_states

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n2o3p4q5r6s7"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_timeline_read_states",
        sa.Column("needs_reply_dismissed_up_to_message_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_job_timeline_read_dismissed_message",
        "job_timeline_read_states",
        "messages",
        ["needs_reply_dismissed_up_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_job_timeline_read_dismissed_message",
        "job_timeline_read_states",
        type_="foreignkey",
    )
    op.drop_column("job_timeline_read_states", "needs_reply_dismissed_up_to_message_id")
