"""Pydantic schemas for job merge suggestions."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class MergeSuggestionJobSummary(BaseModel):
    id: uuid.UUID
    company: str | None
    role: str | None
    current_stage: str

    model_config = {"from_attributes": True}


class MergeSuggestionOut(BaseModel):
    id: uuid.UUID
    source_job: MergeSuggestionJobSummary
    target_job: MergeSuggestionJobSummary
    reason: str
    confidence: float | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MergeSuggestionListResponse(BaseModel):
    items: list[MergeSuggestionOut]
    total: int


class MergeApplyResult(BaseModel):
    merged_job_id: uuid.UUID
    removed_job_id: uuid.UUID
    status: str
