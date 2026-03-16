"""Pydantic schemas for the alerts feed."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AlertJobListing(BaseModel):
    """Matches stored extraction output (AlertJobItem); company/role may be omitted."""

    company: str | None = None
    role: str | None = None
    location: str | None = None
    url: str | None = None


class AlertItem(BaseModel):
    id: uuid.UUID
    subject: str | None
    from_address: str | None
    date_header: datetime | None
    body_snippet: str | None
    category: str | None
    provider_msg_id: str | None = None
    jobs: list[AlertJobListing] = []

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    items: list[AlertItem]
    total: int
