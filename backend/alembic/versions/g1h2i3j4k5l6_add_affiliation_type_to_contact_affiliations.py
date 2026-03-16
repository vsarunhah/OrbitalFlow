"""add affiliation_type to contact_affiliations

Revision ID: g1h2i3j4k5l6
Revises: b2c3d4e5f8a9
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contact_affiliations",
        sa.Column("affiliation_type", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contact_affiliations", "affiliation_type")
