"""Pydantic schemas for jobs, stage transitions, and API responses."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobStage(str, enum.Enum):
    SOURCED = "SOURCED"
    APPLIED = "APPLIED"
    SCREEN = "SCREEN"
    INTERVIEW = "INTERVIEW"
    TAKEHOME = "TAKEHOME"
    FINAL = "FINAL"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


STAGE_ORDINAL: dict[JobStage, int] = {
    JobStage.SOURCED: 0,
    JobStage.APPLIED: 1,
    JobStage.SCREEN: 2,
    JobStage.INTERVIEW: 3,
    JobStage.TAKEHOME: 4,
    JobStage.FINAL: 5,
    JobStage.OFFER: 6,
}

TERMINAL_STAGES = frozenset({JobStage.REJECTED, JobStage.WITHDRAWN})

CONFIDENCE_THRESHOLD = 0.80


# --------------- API request / response schemas ---------------

class JobUpdate(BaseModel):
    company: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=255)
    req_id: str | None = Field(None, max_length=128)


class NextAction(BaseModel):
    type: str
    label: str
    due_at: datetime | None = None
    scheduling_link: str | None = None


class ManualStageChange(BaseModel):
    new_stage: JobStage
    reason: str = Field(max_length=512)


class TimelineReadStateBody(BaseModel):
    read: bool = Field(..., description="True = mark timeline read (caught up); false = mark unread")


class JobSummary(BaseModel):
    id: uuid.UUID
    company: str | None
    role: str | None
    req_id: str | None
    current_stage: str
    confidence: float | None
    last_activity: datetime | None
    next_action: NextAction | None = None
    suggest_followup: bool = Field(
        False,
        description="When true, show 'Generate Follow-Up' (job is stalled or ghosted)",
    )
    unread_incoming_count: int = Field(
        0,
        description="Inbound emails on this job since you last opened its timeline",
    )
    created_at: datetime

    model_config = {"from_attributes": True}


class JobDetail(JobSummary):
    tenant_id: uuid.UUID


class TimelineEvent(BaseModel):
    id: uuid.UUID
    event_type: str | None
    stage_before: str | None
    stage_after: str | None
    confidence: float | None
    source: str
    message_id: uuid.UUID | None
    rationale: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineAttachment(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str | None = None
    size_bytes: int | None = None

    model_config = {"from_attributes": True}


class TimelineMessage(BaseModel):
    id: uuid.UUID
    subject: str | None
    from_address: str | None
    date_header: datetime | None
    body_text: str | None = Field(
        None,
        description="Full body for display (quoted replies stripped); use for in-app reading",
    )
    body_snippet: str | None = Field(
        None, description="First ~300 chars of body_text (quoted replies stripped)"
    )
    body_html: str | None = Field(
        None,
        description="Original HTML body when available; sanitize before rendering in the client",
    )
    provider_msg_id: str | None = Field(
        None, description="Gmail message ID, used to construct a link to the email"
    )
    attachments: list[TimelineAttachment] = Field(
        default_factory=list,
        description="Files attached to this email only (not job-wide)",
    )

    model_config = {"from_attributes": True}


class TimelineSentMessage(BaseModel):
    """Sent reply in timeline (human-in-the-loop send from app)."""
    id: uuid.UUID
    subject: str | None
    to_addrs_json: str = Field(..., description="JSON array of To addresses")
    body_text: str | None = Field(None, description="Full body for in-app display")
    body_snippet: str | None = Field(None, description="First ~300 chars of body_text")
    provider_message_id: str | None = None
    sent_at: datetime

    model_config = {"from_attributes": True}


class JobTimeline(BaseModel):
    job: JobDetail
    events: list[TimelineEvent]
    messages: list[TimelineMessage]
    sent_messages: list[TimelineSentMessage] = Field(
        default_factory=list,
        description="Replies sent from the app (audit)",
    )


class JobListResponse(BaseModel):
    items: list[JobSummary]
    total: int


class JobsMergeRequest(BaseModel):
    """Request to manually merge multiple jobs into one."""

    target_job_id: uuid.UUID = Field(..., description="Job to keep; others will be merged into it")
    source_job_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Job IDs to merge into the target (will be removed)",
    )


class JobsMergeResult(BaseModel):
    merged_job_id: uuid.UUID
    removed_job_ids: list[uuid.UUID]
    status: str = "merged"


class ImportEmailLinkRequest(BaseModel):
    email_url: str = Field(..., min_length=1, max_length=4096)
    job_id: uuid.UUID | None = Field(
        None, description="Existing job to attach the email to; omit to create a new job"
    )
    company: str | None = Field(
        None, max_length=255, description="Optional company name when creating a new job"
    )
    role: str | None = Field(
        None, max_length=255, description="Optional role when creating a new job"
    )


class ImportEmailLinkResult(BaseModel):
    job_id: uuid.UUID
    job_created: bool
    messages_ingested: int
    messages_linked: int
    thread_ids: list[str] = Field(default_factory=list)
