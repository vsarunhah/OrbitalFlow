import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

DEFAULT_LABEL_STATUS = "JobTracker/Status"
DEFAULT_LABEL_RECRUITER = "JobTracker/Recruiter"
DEFAULT_LABEL_ALERTS = "JobTracker/Alerts"
DEFAULT_CONFIDENCE_THRESHOLD = 0.75


class TenantSettings(Base):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_settings_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, unique=True
    )

    labeling_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    labeling_confidence_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=DEFAULT_CONFIDENCE_THRESHOLD
    )

    label_status: Mapped[str] = mapped_column(
        String(255), nullable=False, default=DEFAULT_LABEL_STATUS
    )
    label_recruiter: Mapped[str] = mapped_column(
        String(255), nullable=False, default=DEFAULT_LABEL_RECRUITER
    )
    label_alerts: Mapped[str] = mapped_column(
        String(255), nullable=False, default=DEFAULT_LABEL_ALERTS
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
