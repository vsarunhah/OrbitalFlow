"""Pydantic schemas for message drafts and send API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DraftReplyRequest(BaseModel):
    """Request body for POST /jobs/{id}/draft-reply."""
    source_message_id: uuid.UUID | None = Field(
        None, description="Message we are replying to (optional)"
    )
    tone: str = Field(
        "professional",
        description="Tone preset: professional, warm, concise, enthusiastic, direct",
    )
    user_instruction: str | None = Field(
        None,
        max_length=1000,
        description="Optional instruction e.g. 'say I'm interested', 'ask for compensation range'",
    )


class DraftReplyResult(BaseModel):
    """LLM reply generation output (subject, body, tone, confidence)."""
    subject: str
    body: str
    tone: str | None = None
    confidence: float | None = None


class FollowUpSuggestionResponse(BaseModel):
    """Response from POST /jobs/{id}/follow-up-suggestion: suggestion + optional draft."""
    subject: str
    body: str
    tone: str | None = None
    confidence: float | None = None
    draft: MessageDraftSchema | None = Field(
        None,
        description="Created draft (type follow_up) for editing/sending",
    )


class ReplyVariantSchema(BaseModel):
    """One reply variant (concise / warm / enthusiastic / reject)."""
    variant_id: str
    tone: str
    subject: str
    body: str
    confidence: float | None = None  # LLM sometimes omits; default for display


class DraftReplyResponse(BaseModel):
    """Response for POST /jobs/{id}/draft-reply: draft plus variants."""
    draft: "MessageDraftSchema"
    variants: list[ReplyVariantSchema]


class ClearJobDraftsResponse(BaseModel):
    """Response for DELETE /jobs/{id}/drafts."""
    deleted_count: int = Field(description="Number of unsent drafts removed")


class DraftUpdate(BaseModel):
    """Request body for PATCH /drafts/{id}."""
    subject: str | None = Field(None, max_length=2000)
    body_text: str | None = None


class DraftRecipientsResponse(BaseModel):
    """Response for GET /drafts/{id}/recipients. Default reply-all To/CC; user may remove before send."""
    to_addrs: list[str] = Field(default_factory=list, description="To addresses")
    cc_addrs: list[str] = Field(default_factory=list, description="CC addresses")


class SendDraftRequest(BaseModel):
    """Optional request body for POST /drafts/{id}/send. If provided, use these recipients instead of default reply-all."""
    to_addrs: list[str] | None = Field(None, description="Override To (e.g. after user removed some)")
    cc_addrs: list[str] | None = Field(None, description="Override CC (e.g. after user removed some)")


class ComposeDraftRequest(BaseModel):
    """Request body for POST /jobs/{id}/compose-draft. Create a draft without AI (user types subject/body)."""
    source_message_id: uuid.UUID | None = Field(None, description="Message being replied to (for reply-all defaults)")
    subject: str | None = Field(None, max_length=2000)
    body_text: str | None = Field(None, description="Plain text body")


class MessageDraftSchema(BaseModel):
    """Draft as returned by API."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    source_message_id: uuid.UUID | None
    account_id: uuid.UUID
    draft_type: str
    subject: str | None
    body_text: str | None
    tone: str | None
    status: str
    variants: list[ReplyVariantSchema] | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SentMessageSchema(BaseModel):
    """Sent message as returned in timeline or audit."""
    id: uuid.UUID
    job_id: uuid.UUID
    account_id: uuid.UUID
    provider: str
    provider_message_id: str | None
    thread_id: str | None
    to_addrs_json: str
    cc_addrs_json: str | None
    subject: str | None
    body_text: str | None
    sent_at: datetime

    model_config = {"from_attributes": True}
