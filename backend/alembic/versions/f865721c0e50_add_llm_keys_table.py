"""add llm_keys table

Revision ID: f865721c0e50
Revises: 4553cf4953dc
Create Date: 2026-02-24 00:36:53.363593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f865721c0e50'
down_revision: Union[str, Sequence[str], None] = '4553cf4953dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('llm_keys',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('encrypted_key', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('llm_keys')
