"""Per-user job-search preferences used by AI draft generation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

COMPANY_SIZE_CHOICES = ("startup", "small", "mid", "large", "enterprise")
WORK_ARRANGEMENT_CHOICES = ("remote", "hybrid", "onsite", "flexible")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False
    )

    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_arrangements: Mapped[list | None] = mapped_column(JSON, nullable=True)
    compensation_expectations: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_company_sizes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    availability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
