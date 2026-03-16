"""Pydantic schemas for analytics API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    """One-shot summary of job/application metrics."""

    total_jobs: int = Field(..., description="Total tracked jobs for the tenant")
    by_stage: dict[str, int] = Field(
        ...,
        description="Count of jobs per current_stage (e.g. APPLIED, INTERVIEW)",
    )
    applications_received: int = Field(
        ...,
        description="Number of distinct jobs with at least one APPLICATION_RECEIVED event",
    )
    interviews_detected: int = Field(
        ...,
        description="Number of distinct jobs with at least one INTERVIEW_* event",
    )
    offers: int = Field(
        ...,
        description="Number of distinct jobs with OFFER event or current_stage OFFER",
    )
    rejections: int = Field(
        ...,
        description="Number of jobs with current_stage REJECTED",
    )
    conversion_application_to_interview: float = Field(
        ...,
        description="interviews_detected / applications_received, 0 if no applications",
    )
    conversion_interview_to_offer: float = Field(
        ...,
        description="offers / interviews_detected, 0 if no interviews",
    )
    avg_days_applied_to_first_interview: float | None = Field(
        None,
        description="Average days from first APPLICATION_RECEIVED to first INTERVIEW_* event; null if no jobs with both",
    )
    recent_activity_7d: int = Field(
        ...,
        description="Count of job_events in the last 7 days",
    )
    recent_activity_30d: int = Field(
        ...,
        description="Count of job_events in the last 30 days",
    )


class AnalyticsFunnel(BaseModel):
    """Funnel breakdown: milestone counts and by current stage."""

    milestones: dict[str, int] = Field(
        ...,
        description="Counts at funnel steps: applied, interview, offer, rejected",
    )
    by_stage: dict[str, int] = Field(
        ...,
        description="Count of jobs per current_stage",
    )


class FunnelFlowLink(BaseModel):
    """Single flow edge for Sankey: from stage -> to stage with count."""

    from_stage: str = Field(..., description="Source stage name")
    to_stage: str = Field(..., description="Target stage name")
    value: int = Field(..., description="Number of jobs that moved along this edge")


class AnalyticsFunnelFlow(BaseModel):
    """Flow data for Sankey-style funnel: transitions between stages."""

    flows: list[FunnelFlowLink] = Field(
        default_factory=list,
        description="List of (from_stage, to_stage, value) for diagram links",
    )


class TimeseriesPoint(BaseModel):
    """Single date bucket for timeseries."""

    date: str = Field(..., description="Date string YYYY-MM-DD")
    count: int = Field(..., description="Count for that date")


class AnalyticsTimeseries(BaseModel):
    """Time series of jobs created and/or activity."""

    window: str = Field(..., description="Requested window: 7d, 30d, or 90d")
    jobs_created: list[TimeseriesPoint] = Field(
        default_factory=list,
        description="Jobs created per day",
    )
    activity: list[TimeseriesPoint] = Field(
        default_factory=list,
        description="Job events (activity) per day",
    )
