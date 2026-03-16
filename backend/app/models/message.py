import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    types,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TSVector(types.TypeDecorator):
    """TSVECTOR on Postgres, plain TEXT on other dialects (e.g. SQLite for tests)."""

    impl = types.Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import TSVECTOR

            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(types.Text())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_msg_id", name="uq_account_provider_msg"),
        Index("ix_messages_tenant_id", "tenant_id"),
        Index("ix_messages_account_id", "account_id"),
        Index("ix_messages_thread_id", "thread_id"),
        Index("ix_messages_date_header", "date_header"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("email_accounts.id"), nullable=False
    )
    provider_msg_id: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_addresses: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_header: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    label_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    body_text_tsv = mapped_column(TSVector, nullable=True)

    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
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
