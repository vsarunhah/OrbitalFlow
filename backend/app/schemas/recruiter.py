"""Pydantic schemas for the recruiters view."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AffiliationOut(BaseModel):
    id: uuid.UUID
    company: str | None
    title: str | None
    affiliation_type: str | None = None  # "agency" | "company" | null
    created_at: datetime

    model_config = {"from_attributes": True}


class RecruiterJobOut(BaseModel):
    job_id: uuid.UUID
    company: str | None
    role: str | None
    current_stage: str
    contact_role: str

    model_config = {"from_attributes": True}


class RecruiterSummary(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str
    affiliations: list[AffiliationOut]
    job_count: int
    message_count: int = 0
    company_count: int = 0
    primary_agency: str | None = None

    model_config = {"from_attributes": True}


class RecruiterDetail(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str
    phone: str | None
    affiliations: list[AffiliationOut]
    jobs: list[RecruiterJobOut]
    created_at: datetime
    message_count: int = 0
    company_count: int = 0
    primary_agency: str | None = None
    companies: list[str] = []  # distinct companies (affiliations + jobs), sorted

    model_config = {"from_attributes": True}


class RecruiterListResponse(BaseModel):
    items: list[RecruiterSummary]
    total: int


class RecruitersMergeRequest(BaseModel):
    """Request to manually merge multiple recruiters (contacts) into one."""

    target_contact_id: uuid.UUID = Field(
        ..., description="Recruiter/contact to keep; others will be merged into it"
    )
    source_contact_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Contact IDs to merge into the target (will be removed)",
    )


class RecruitersMergeResult(BaseModel):
    merged_contact_id: uuid.UUID
    removed_contact_ids: list[uuid.UUID]
    status: str = "merged"
