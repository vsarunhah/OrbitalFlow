"""Shared calendar availability logic for API and draft agent tools."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message
from app.providers.google_calendar import (
    CalendarAuthError,
    GoogleCalendarProvider,
    TokenRefreshError,
    account_has_calendar_scope,
    compute_availability_slots,
)
from app.providers.gmail import TokenRefreshError as GmailTokenRefreshError


def resolve_calendar_account_for_job(
    db: Session, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> EmailAccount | None:
    thread_ids = [
        row[0]
        for row in db.query(JobThread.thread_id)
        .filter(JobThread.job_id == job_id, JobThread.tenant_id == tenant_id)
        .all()
        if row[0]
    ]
    if thread_ids:
        msg = (
            db.query(Message)
            .filter(Message.tenant_id == tenant_id, Message.thread_id.in_(thread_ids))
            .first()
        )
        if msg and msg.account_id:
            account = (
                db.query(EmailAccount)
                .filter(
                    EmailAccount.id == msg.account_id,
                    EmailAccount.tenant_id == tenant_id,
                    EmailAccount.status == "active",
                )
                .first()
            )
            if account:
                return account

    event = (
        db.query(JobEvent)
        .filter(
            JobEvent.job_id == job_id,
            JobEvent.tenant_id == tenant_id,
            JobEvent.message_id.isnot(None),
        )
        .first()
    )
    if event and event.message_id:
        msg = (
            db.query(Message)
            .filter(Message.id == event.message_id, Message.tenant_id == tenant_id)
            .first()
        )
        if msg and msg.account_id:
            return (
                db.query(EmailAccount)
                .filter(
                    EmailAccount.id == msg.account_id,
                    EmailAccount.tenant_id == tenant_id,
                    EmailAccount.status == "active",
                )
                .first()
            )
    return (
        db.query(EmailAccount)
        .filter(
            EmailAccount.tenant_id == tenant_id,
            EmailAccount.status == "active",
            EmailAccount.provider == "gmail",
        )
        .order_by(EmailAccount.created_at)
        .first()
    )


def resolve_date_range(
    *,
    timezone_name: str,
    now: datetime,
    date_start: date | None,
    date_end: date | None,
    default_days: int = 7,
) -> tuple[date, date]:
    if date_start is not None and date_end is not None:
        return date_start, date_end
    z = ZoneInfo(timezone_name)
    local_today = now.astimezone(z).date()
    d = max(1, default_days)
    return local_today, local_today + timedelta(days=d - 1)


def fetch_availability_for_agent(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    timezone_name: str,
    date_start: date | None = None,
    date_end: date | None = None,
    duration_minutes: int = 30,
    default_days: int = 7,
) -> dict:
    """
    Return JSON-serializable availability for the draft agent tool.
    Never raises HTTP exceptions; errors are encoded in the result dict.
    """
    now = datetime.now(timezone.utc)
    try:
        range_start, range_end = resolve_date_range(
            timezone_name=timezone_name,
            now=now,
            date_start=date_start,
            date_end=date_end,
            default_days=default_days,
        )
    except (ValueError, ZoneInfoNotFoundError) as e:
        return {"error": str(e) or "Invalid timezone or date range", "slots": []}

    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == tenant_id)
        .first()
    )
    if not job:
        return {"error": "Job not found", "slots": []}

    account = resolve_calendar_account_for_job(db, tenant_id, job_id)
    if not account:
        return {
            "error": "No email account available for calendar.",
            "slots": [],
            "calendar_connected": False,
        }

    if not account_has_calendar_scope(account):
        return {
            "calendar_connected": False,
            "detail": "Google Calendar is not connected. Use availability_notes from profile or ask the user to connect Calendar.",
            "slots": [],
            "timezone": timezone_name,
            "date_start": range_start.isoformat(),
            "date_end": range_end.isoformat(),
        }

    try:
        tz = ZoneInfo(timezone_name)
        time_min = datetime.combine(range_start, time.min, tzinfo=tz) - timedelta(days=1)
        time_max = datetime.combine(range_end, time.max, tzinfo=tz) + timedelta(days=1)
        busy, calendar_errors = GoogleCalendarProvider(db_session=db).fetch_busy_intervals(
            account,
            time_min=time_min,
            time_max=time_max,
            calendar_ids=["primary"],
            timezone_name=timezone_name,
        )
        slots = compute_availability_slots(
            busy_intervals=busy,
            now=now,
            timezone_name=timezone_name,
            range_start_date=range_start,
            range_end_date=range_end,
            duration_minutes=duration_minutes,
            workday_start=time(9, 0),
            workday_end=time(17, 0),
            slot_granularity_minutes=30,
            min_notice_minutes=60,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )
    except (CalendarAuthError, TokenRefreshError, GmailTokenRefreshError) as e:
        return {
            "calendar_connected": False,
            "error": str(e) or "Calendar authentication failed",
            "slots": [],
        }
    except ValueError as e:
        return {"error": str(e), "slots": []}

    return {
        "calendar_connected": True,
        "timezone": timezone_name,
        "date_start": range_start.isoformat(),
        "date_end": range_end.isoformat(),
        "duration_minutes": duration_minutes,
        "slots": [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "display": slot.display,
            }
            for slot in slots[:12]
        ],
        "total_slots": len(slots),
        "calendar_errors": calendar_errors,
    }
