"""add FTS tsvector column + GIN index on messages.body_text

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-24 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("body_text_tsv", TSVECTOR, nullable=True))

    op.execute(
        "UPDATE messages SET body_text_tsv = to_tsvector('english', coalesce(body_text, ''))"
    )

    op.execute(
        "CREATE INDEX ix_messages_body_text_fts ON messages USING gin(body_text_tsv)"
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION messages_body_text_tsv_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.body_text_tsv := to_tsvector('english', coalesce(NEW.body_text, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_messages_body_text_tsv
        BEFORE INSERT OR UPDATE OF body_text ON messages
        FOR EACH ROW EXECUTE FUNCTION messages_body_text_tsv_trigger();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_messages_body_text_tsv ON messages")
    op.execute("DROP FUNCTION IF EXISTS messages_body_text_tsv_trigger()")
    op.execute("DROP INDEX IF EXISTS ix_messages_body_text_fts")
    op.drop_column("messages", "body_text_tsv")
