"""add Phase 9 contacts, affiliations, job_contacts, merge_suggestions tables

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-02-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(320), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_contacts_tenant_email"),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])

    op.create_table(
        "contact_affiliations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_contact_affiliations_contact_id", "contact_affiliations", ["contact_id"]
    )
    op.create_index(
        "ix_contact_affiliations_tenant_id", "contact_affiliations", ["tenant_id"]
    )

    op.create_table(
        "job_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=False, server_default="recruiter"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "job_id", "contact_id", name="uq_job_contacts_tenant_job_contact"
        ),
    )
    op.create_index("ix_job_contacts_tenant_id", "job_contacts", ["tenant_id"])
    op.create_index("ix_job_contacts_job_id", "job_contacts", ["job_id"])
    op.create_index("ix_job_contacts_contact_id", "job_contacts", ["contact_id"])

    op.create_table(
        "job_merge_suggestions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "source_job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_job_merge_suggestions_tenant_id", "job_merge_suggestions", ["tenant_id"]
    )
    op.create_index(
        "ix_job_merge_suggestions_status",
        "job_merge_suggestions",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("job_merge_suggestions")
    op.drop_table("job_contacts")
    op.drop_table("contact_affiliations")
    op.drop_table("contacts")
