"""add alert_jobs_json column to message_extractions

Revision ID: b2c3d4e5f8a9
Revises: a1b2c3d4e5f7
Create Date: 2026-02-25 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f8a9"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message_extractions",
        sa.Column("alert_jobs_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("message_extractions", "alert_jobs_json")
