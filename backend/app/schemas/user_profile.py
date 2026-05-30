"""Schemas for job-seeker profile (draft agent + settings)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models.user_profile import COMPANY_SIZE_CHOICES, WORK_ARRANGEMENT_CHOICES


class UserProfileSchema(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    location_preferences: str | None = None
    work_arrangements: list[str] = Field(default_factory=list)
    compensation_expectations: str | None = None
    preferred_company_sizes: list[str] = Field(default_factory=list)
    availability_notes: str | None = None

    @field_validator("preferred_company_sizes", mode="before")
    @classmethod
    def normalize_company_sizes(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        allowed = set(COMPANY_SIZE_CHOICES)
        return [s for s in v if s in allowed]

    @field_validator("work_arrangements", mode="before")
    @classmethod
    def normalize_work_arrangements(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        allowed = set(WORK_ARRANGEMENT_CHOICES)
        return [s for s in v if s in allowed]


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    location_preferences: str | None = None
    work_arrangements: list[str] | None = None
    compensation_expectations: str | None = None
    preferred_company_sizes: list[str] | None = None
    availability_notes: str | None = None

    @field_validator("preferred_company_sizes", mode="before")
    @classmethod
    def normalize_company_sizes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        allowed = set(COMPANY_SIZE_CHOICES)
        return [s for s in v if s in allowed]

    @field_validator("work_arrangements", mode="before")
    @classmethod
    def normalize_work_arrangements(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        allowed = set(WORK_ARRANGEMENT_CHOICES)
        return [s for s in v if s in allowed]
