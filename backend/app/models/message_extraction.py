import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageExtraction(Base):
    __tablename__ = "message_extractions"
    __table_args__ = (
        Index("ix_msg_ext_tenant_id", "tenant_id"),
        Index("ix_msg_ext_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id"), nullable=False
    )

    # Classification fields
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    req_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM metadata
    llm_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extracted job listings from ALERT emails (JSON array)
    alert_jobs_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Safe snippet of raw LLM response for debugging (never full body)
    raw_response_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
