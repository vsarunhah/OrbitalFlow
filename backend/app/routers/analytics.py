"""Analytics API: summary, funnel, and timeseries metrics from jobs and job_events."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.job import Job, JobEvent, JobStageHistory
from app.schemas.analytics import (
    AnalyticsFunnel,
    AnalyticsFunnelFlow,
    AnalyticsSummary,
    AnalyticsTimeseries,
    FunnelFlowLink,
    TimeseriesPoint,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Event type groups used for metrics
EVENT_APPLICATION = "APPLICATION_RECEIVED"
EVENT_INTERVIEW_TYPES = (
    "INTERVIEW_REQUEST",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_RESCHEDULE",
)
EVENT_OFFER = "OFFER"
STAGE_OFFER = "OFFER"
STAGE_REJECTED = "REJECTED"


def _offers_subq(db: Session, tenant_id: uuid.UUID):
    """Subquery: job_ids that have at least one OFFER event."""
    return (
        db.query(JobEvent.job_id)
        .filter(
            JobEvent.tenant_id == tenant_id,
            JobEvent.event_type == EVENT_OFFER,
        )
        .distinct()
        .subquery()
    )


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return one-shot summary: total jobs, by stage, applications, interviews, offers, rejections, conversion rates, avg days, recent activity."""

    # Total jobs
    total_jobs = db.query(Job).filter(Job.tenant_id == auth.tenant_id).count()

    # By current_stage
    stage_rows = (
        db.query(Job.current_stage, sa_func.count(Job.id))
        .filter(Job.tenant_id == auth.tenant_id)
        .group_by(Job.current_stage)
        .all()
    )
    by_stage = {row[0]: row[1] for row in stage_rows}

    # Applications received (distinct jobs with APPLICATION_RECEIVED)
    applications_received = (
        db.query(sa_func.count(sa_func.distinct(JobEvent.job_id)))
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.event_type == EVENT_APPLICATION,
        )
        .scalar()
        or 0
    )

    # Interviews detected (distinct jobs with INTERVIEW_*)
    interviews_detected = (
        db.query(sa_func.count(sa_func.distinct(JobEvent.job_id)))
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.event_type.in_(EVENT_INTERVIEW_TYPES),
        )
        .scalar()
        or 0
    )

    # Offers: distinct jobs with OFFER event or current_stage OFFER
    offer_event_job_ids = _offers_subq(db, auth.tenant_id)
    offer_job_ids = set(
        row[0] for row in db.query(offer_event_job_ids.c.job_id).all()
    )
    for row in (
        db.query(Job.id)
        .filter(Job.tenant_id == auth.tenant_id, Job.current_stage == STAGE_OFFER)
        .all()
    ):
        offer_job_ids.add(row[0])
    offers = len(offer_job_ids)

    # Rejections: jobs with current_stage REJECTED
    rejections = (
        db.query(Job.id)
        .filter(
            Job.tenant_id == auth.tenant_id,
            Job.current_stage == STAGE_REJECTED,
        )
        .count()
    )

    # Conversion rates
    conversion_app_to_int = (
        (interviews_detected / applications_received)
        if applications_received else 0.0
    )
    conversion_int_to_offer = (
        (offers / interviews_detected) if interviews_detected else 0.0
    )

    # Avg days applied -> first interview (per job: first APPLICATION_RECEIVED time, first INTERVIEW_* time)
    # Get per-job min(created_at) for APPLICATION_RECEIVED and for INTERVIEW_*
    app_times = (
        db.query(
            JobEvent.job_id,
            sa_func.min(JobEvent.created_at).label("first_at"),
        )
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.event_type == EVENT_APPLICATION,
        )
        .group_by(JobEvent.job_id)
        .subquery()
    )
    int_times = (
        db.query(
            JobEvent.job_id,
            sa_func.min(JobEvent.created_at).label("first_at"),
        )
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.event_type.in_(EVENT_INTERVIEW_TYPES),
        )
        .group_by(JobEvent.job_id)
        .subquery()
    )
    # Join on job_id; for each job with both, compute days between first app and first interview
    joined = (
        db.query(app_times.c.first_at.label("app_at"), int_times.c.first_at.label("int_at"))
        .join(
            int_times,
            app_times.c.job_id == int_times.c.job_id,
        )
        .all()
    )
    days_list = []
    for app_dt, int_dt in joined:
        if app_dt and int_dt:
            delta = int_dt - app_dt
            days_list.append(delta.total_seconds() / 86400.0)
    avg_days_applied_to_first_interview = (
        sum(days_list) / len(days_list) if days_list else None
    )

    # Recent activity: count job_events in last 7d and 30d
    now = datetime.now(timezone.utc)
    since_7 = now - timedelta(days=7)
    since_30 = now - timedelta(days=30)
    recent_activity_7d = (
        db.query(JobEvent.id)
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.created_at >= since_7,
        )
        .count()
    )
    recent_activity_30d = (
        db.query(JobEvent.id)
        .filter(
            JobEvent.tenant_id == auth.tenant_id,
            JobEvent.created_at >= since_30,
        )
        .count()
    )

    return AnalyticsSummary(
        total_jobs=total_jobs,
        by_stage=by_stage,
        applications_received=applications_received,
        interviews_detected=interviews_detected,
        offers=offers,
        rejections=rejections,
        conversion_application_to_interview=round(
            conversion_app_to_int, 4
        ),
        conversion_interview_to_offer=round(conversion_int_to_offer, 4),
        avg_days_applied_to_first_interview=round(
            avg_days_applied_to_first_interview, 2
        )
        if avg_days_applied_to_first_interview is not None
        else None,
        recent_activity_7d=recent_activity_7d,
        recent_activity_30d=recent_activity_30d,
    )


@router.get("/funnel", response_model=AnalyticsFunnel)
def get_funnel(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return funnel: milestone counts (applied, interview, offer, rejected) and by_stage."""
    tenant_id = auth.tenant_id

    applied = (
        db.query(JobEvent.job_id)
        .filter(
            JobEvent.tenant_id == tenant_id,
            JobEvent.event_type == EVENT_APPLICATION,
        )
        .distinct()
        .count()
    )
    interview = (
        db.query(JobEvent.job_id)
        .filter(
            JobEvent.tenant_id == tenant_id,
            JobEvent.event_type.in_(EVENT_INTERVIEW_TYPES),
        )
        .distinct()
        .count()
    )
    offer_event_job_ids = _offers_subq(db, tenant_id)
    offer_job_set = set(row[0] for row in db.query(offer_event_job_ids.c.job_id).all())
    for row in (
        db.query(Job.id)
        .filter(Job.tenant_id == tenant_id, Job.current_stage == STAGE_OFFER)
        .all()
    ):
        offer_job_set.add(row[0])
    offer = len(offer_job_set)
    rejected = (
        db.query(Job.id)
        .filter(
            Job.tenant_id == tenant_id,
            Job.current_stage == STAGE_REJECTED,
        )
        .count()
    )

    stage_rows = (
        db.query(Job.current_stage, sa_func.count(Job.id))
        .filter(Job.tenant_id == tenant_id)
        .group_by(Job.current_stage)
        .all()
    )
    by_stage = {row[0]: row[1] for row in stage_rows}

    return AnalyticsFunnel(
        milestones={
            "applied": applied,
            "interview": interview,
            "offer": offer,
            "rejected": rejected,
        },
        by_stage=by_stage,
    )


@router.get("/funnel-flow", response_model=AnalyticsFunnelFlow)
def get_funnel_flow(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return stage-to-stage flow counts for Sankey. SOURCED and APPLIED are root nodes; only forward transitions are included."""
    tenant_id = auth.tenant_id

    transition_rows = (
        db.query(
            JobStageHistory.stage_before,
            JobStageHistory.stage_after,
            sa_func.count(JobStageHistory.id).label("cnt"),
        )
        .filter(JobStageHistory.tenant_id == tenant_id)
        .group_by(JobStageHistory.stage_before, JobStageHistory.stage_after)
        .all()
    )
    flows: list[FunnelFlowLink] = [
        FunnelFlowLink(from_stage=row[0], to_stage=row[1], value=row[2])
        for row in transition_rows
        if row[2] and row[0] and row[1]
    ]

    return AnalyticsFunnelFlow(flows=flows)


def _to_date_iso(dt) -> str | None:
    """Normalize a datetime to YYYY-MM-DD string (DB-agnostic)."""
    if dt is None:
        return None
    if hasattr(dt, "date"):
        return dt.date().isoformat()
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).date().isoformat()
        except (ValueError, TypeError):
            return dt[:10] if len(dt) >= 10 else None
    return None


def _timeseries_group_by_date_in_python(
    db: Session,
    tenant_id,
    since: datetime,
    job_created: bool,
    event_activity: bool,
):
    """Return (jobs_created_list, activity_list). Uses Python grouping for DB compatibility."""
    jobs_by_date = defaultdict(int)
    activity_by_date = defaultdict(int)

    if job_created:
        rows = (
            db.query(Job.created_at)
            .filter(
                Job.tenant_id == tenant_id,
                Job.created_at >= since,
            )
            .all()
        )
        for (dt,) in rows:
            key = _to_date_iso(dt)
            if key:
                jobs_by_date[key] += 1

    if event_activity:
        rows = (
            db.query(JobEvent.created_at)
            .filter(
                JobEvent.tenant_id == tenant_id,
                JobEvent.created_at >= since,
            )
            .all()
        )
        for (dt,) in rows:
            key = _to_date_iso(dt)
            if key:
                activity_by_date[key] += 1

    all_dates = sorted(set(jobs_by_date.keys()) | set(activity_by_date.keys()))
    jobs_created_list = [TimeseriesPoint(date=d, count=jobs_by_date[d]) for d in all_dates]
    activity_list = [TimeseriesPoint(date=d, count=activity_by_date[d]) for d in all_dates]
    return jobs_created_list, activity_list


@router.get("/timeseries", response_model=AnalyticsTimeseries)
def get_timeseries(
    window: Literal["7d", "30d", "90d"] = Query("30d", description="Window: 7d, 30d, or 90d"),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return time series: jobs created per day and activity (job_events) per day."""
    tenant_id = auth.tenant_id
    days = 7 if window == "7d" else (30 if window == "30d" else 90)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    jobs_created_list, activity_list = _timeseries_group_by_date_in_python(
        db, tenant_id, since, job_created=True, event_activity=True
    )

    return AnalyticsTimeseries(
        window=window,
        jobs_created=jobs_created_list,
        activity=activity_list,
    )
