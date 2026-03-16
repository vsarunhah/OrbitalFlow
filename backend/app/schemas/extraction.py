"""Pydantic schemas for LLM extraction output.

These schemas define the strict JSON contract the LLM must conform to.
Invalid output is caught via pydantic validation and retried / marked failed.
"""

from __future__ import annotations

import enum
from pydantic import BaseModel, Field


class Category(str, enum.Enum):
    STATUS = "STATUS"
    RECRUITER = "RECRUITER"
    ALERT = "ALERT"
    OTHER = "OTHER"


class EventType(str, enum.Enum):
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    INTERVIEW_REQUEST = "INTERVIEW_REQUEST"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_RESCHEDULE = "INTERVIEW_RESCHEDULE"
    TAKEHOME_REQUEST = "TAKEHOME_REQUEST"
    OFFER = "OFFER"
    REJECTION = "REJECTION"
    FOLLOW_UP = "FOLLOW_UP"
    JOB_ALERT = "JOB_ALERT"
    NONE = "NONE"


class ContactInfo(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None


class AlertJobItem(BaseModel):
    """A single job listing extracted from an alert/digest email."""

    company: str | None = None
    role: str | None = None
    location: str | None = None
    url: str | None = None


class ExtractionResult(BaseModel):
    """Validated structure returned by the LLM for a single email."""

    category: Category
    event_type: EventType
    company: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    req_id: str | None = Field(
        default=None,
        max_length=128,
        description="Requisition / job ID extracted from the email",
    )
    contacts: list[ContactInfo] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(
        max_length=512,
        description="One-sentence explanation of why this classification was chosen",
    )
    jobs: list[AlertJobItem] = Field(
        default_factory=list,
        description="Individual job listings extracted from ALERT emails",
    )
