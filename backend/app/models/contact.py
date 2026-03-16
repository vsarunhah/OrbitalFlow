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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_contacts_tenant_email"),
        Index("ix_contacts_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    affiliations: Mapped[list["ContactAffiliation"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    job_contacts: Mapped[list["JobContact"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )


class ContactAffiliation(Base):
    __tablename__ = "contact_affiliations"
    __table_args__ = (
        Index("ix_contact_affiliations_contact_id", "contact_id"),
        Index("ix_contact_affiliations_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affiliation_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # "agency" | "company" | null

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contact: Mapped["Contact"] = relationship(back_populates="affiliations")


class JobContact(Base):
    __tablename__ = "job_contacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "job_id", "contact_id", name="uq_job_contacts_tenant_job_contact"
        ),
        Index("ix_job_contacts_tenant_id", "tenant_id"),
        Index("ix_job_contacts_job_id", "job_id"),
        Index("ix_job_contacts_contact_id", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(64), nullable=False, default="recruiter"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contact: Mapped["Contact"] = relationship(back_populates="job_contacts")
