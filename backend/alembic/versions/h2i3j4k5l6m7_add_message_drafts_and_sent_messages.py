"""add message_drafts and sent_messages tables (AI reply + send from app)

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-03-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("draft_type", sa.String(32), nullable=False, server_default="reply"),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("tone", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="GENERATED"),
        sa.Column("generation_context_json", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["email_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_drafts_tenant_id", "message_drafts", ["tenant_id"])
    op.create_index("ix_message_drafts_job_id", "message_drafts", ["job_id"])
    op.create_index(
        "ix_message_drafts_tenant_status",
        "message_drafts",
        ["tenant_id", "status"],
    )

    op.create_table(
        "sent_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="gmail"),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("to_addrs_json", sa.Text(), nullable=False),
        sa.Column("cc_addrs_json", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["email_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sent_messages_tenant_id", "sent_messages", ["tenant_id"])
    op.create_index("ix_sent_messages_job_id", "sent_messages", ["job_id"])
    op.create_index("ix_sent_messages_account_id", "sent_messages", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_sent_messages_account_id", table_name="sent_messages")
    op.drop_index("ix_sent_messages_job_id", table_name="sent_messages")
    op.drop_index("ix_sent_messages_tenant_id", table_name="sent_messages")
    op.drop_table("sent_messages")

    op.drop_index("ix_message_drafts_tenant_status", table_name="message_drafts")
    op.drop_index("ix_message_drafts_job_id", table_name="message_drafts")
    op.drop_index("ix_message_drafts_tenant_id", table_name="message_drafts")
    op.drop_table("message_drafts")
