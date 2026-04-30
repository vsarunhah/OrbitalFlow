"""Pydantic schemas for calendar availability APIs."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AvailabilitySlotRequest(BaseModel):
    """Request body for computing available calendar slots."""

    job_id: uuid.UUID | None = Field(
        None,
        description="Optional job id; when present, use the email account tied to the job thread.",
    )
    account_id: uuid.UUID | None = Field(
        None,
        description="Optional explicit email account id. job_id takes precedence.",
    )
    duration_minutes: int = Field(30, ge=15, le=240)
    timezone: str = Field("UTC", min_length=1, max_length=128)
    days: int = Field(7, ge=1, le=30, description="Used only when date_start/date_end are omitted")
    date_start: date | None = Field(
        None,
        description="First calendar day to search (in timezone), inclusive",
    )
    date_end: date | None = Field(
        None,
        description="Last calendar day to search (in timezone), inclusive",
    )
    workday_start: time = Field(default=time(9, 0))
    workday_end: time = Field(default=time(17, 0))
    slot_granularity_minutes: int = Field(30, ge=5, le=120)
    min_notice_minutes: int = Field(60, ge=0, le=7 * 24 * 60)
    buffer_before_minutes: int = Field(0, ge=0, le=240)
    buffer_after_minutes: int = Field(0, ge=0, le=240)
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"], max_length=10)

    @model_validator(mode="after")
    def validate_date_range(self) -> AvailabilitySlotRequest:
        if (self.date_start is None) ^ (self.date_end is None):
            raise ValueError("date_start and date_end must be provided together")
        if self.date_start and self.date_end:
            if self.date_end < self.date_start:
                raise ValueError("date_end must be on or after date_start")
            if (self.date_end - self.date_start).days > 90:
                raise ValueError("date range cannot exceed 90 days")
        return self


class CalendarConnectRequired(BaseModel):
    required: Literal[True] = True
    auth_url: str | None = None
    detail: str


class AvailabilitySlot(BaseModel):
    start: datetime
    end: datetime
    timezone: str
    display: str


class AvailabilitySlotsResponse(BaseModel):
    slots: list[AvailabilitySlot]
    checked_at: datetime
    timezone: str
    date_start: date
    date_end: date
    duration_minutes: int
    calendar_ids: list[str]
    calendar_errors: dict[str, str] = Field(default_factory=dict)
    connect_required: CalendarConnectRequired | None = None
