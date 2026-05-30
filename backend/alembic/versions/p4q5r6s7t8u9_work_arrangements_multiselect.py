"""work_arrangement -> work_arrangements JSON array

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p4q5r6s7t8u9"
down_revision: Union[str, Sequence[str], None] = "o3p4q5r6s7t8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("work_arrangements", sa.JSON(), nullable=True),
    )
    op.execute(
        """
        UPDATE user_profiles
        SET work_arrangements = json_build_array(work_arrangement)::json
        WHERE work_arrangement IS NOT NULL AND work_arrangement != ''
        """
    )
    op.drop_column("user_profiles", "work_arrangement")


def downgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("work_arrangement", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE user_profiles
        SET work_arrangement = work_arrangements->>0
        WHERE work_arrangements IS NOT NULL
          AND json_typeof(work_arrangements) = 'array'
          AND json_array_length(work_arrangements) > 0
        """
    )
    op.drop_column("user_profiles", "work_arrangements")
