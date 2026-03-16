"""Message drafts (AI-suggested replies) and sent_messages audit log."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageDraft(Base):
    """A suggested or edited reply draft. Never auto-sent; user must explicitly send."""

    __tablename__ = "message_drafts"
    __table_args__ = (
        Index("ix_message_drafts_tenant_id", "tenant_id"),
        Index("ix_message_drafts_job_id", "job_id"),
        Index("ix_message_drafts_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id"), nullable=False
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id"), nullable=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("email_accounts.id"), nullable=False
    )
    draft_type: Mapped[str] = mapped_column(String(32), nullable=False, default="reply")
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="GENERATED"
    )  # GENERATED, EDITED, SENT, FAILED
    generation_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    variants_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SentMessage(Base):
    """Audit log of emails sent from the app (human-in-the-loop send)."""

    __tablename__ = "sent_messages"
    __table_args__ = (
        Index("ix_sent_messages_tenant_id", "tenant_id"),
        Index("ix_sent_messages_job_id", "job_id"),
        Index("ix_sent_messages_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("email_accounts.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="gmail")
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_addrs_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    cc_addrs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
