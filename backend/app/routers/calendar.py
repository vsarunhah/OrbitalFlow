"""Calendar availability API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.auth.security import create_access_token
from app.config import settings
from app.database import get_db
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
from app.routers.email_accounts import GOOGLE_CALENDAR_SCOPES, _build_google_auth_url
from app.schemas.calendar import (
    AvailabilitySlotRequest,
    AvailabilitySlotsResponse,
    CalendarConnectRequired,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/availability/slots", response_model=AvailabilitySlotsResponse)
def get_availability_slots(
    body: AvailabilitySlotRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AvailabilitySlotsResponse:
    now = datetime.now(timezone.utc)
    try:
        range_start, range_end = _resolve_date_range(body, now)
    except (ValueError, ZoneInfoNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Invalid timezone or date range",
        ) from e

    account = _resolve_calendar_account(db, auth.tenant_id, body)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email account found for calendar availability.",
        )
    calendar_ids = body.calendar_ids or ["primary"]
    if not account_has_calendar_scope(account):
        return AvailabilitySlotsResponse(
            slots=[],
            checked_at=now,
            timezone=body.timezone,
            date_start=range_start,
            date_end=range_end,
            duration_minutes=body.duration_minutes,
            calendar_ids=calendar_ids,
            connect_required=CalendarConnectRequired(
                auth_url=_calendar_auth_url(auth),
                detail="Connect Google Calendar to view availability.",
            ),
        )
    try:
        tz = ZoneInfo(body.timezone)
        time_min = datetime.combine(range_start, time.min, tzinfo=tz) - timedelta(days=1)
        time_max = datetime.combine(range_end, time.max, tzinfo=tz) + timedelta(days=1)
        busy, calendar_errors = GoogleCalendarProvider(db_session=db).fetch_busy_intervals(
            account,
            time_min=time_min,
            time_max=time_max,
            calendar_ids=calendar_ids,
            timezone_name=body.timezone,
        )
        slots = compute_availability_slots(
            busy_intervals=busy,
            now=now,
            timezone_name=body.timezone,
            range_start_date=range_start,
            range_end_date=range_end,
            duration_minutes=body.duration_minutes,
            workday_start=body.workday_start,
            workday_end=body.workday_end,
            slot_granularity_minutes=body.slot_granularity_minutes,
            min_notice_minutes=body.min_notice_minutes,
            buffer_before_minutes=body.buffer_before_minutes,
            buffer_after_minutes=body.buffer_after_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except (CalendarAuthError, TokenRefreshError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Calendar authentication failed. Reconnect Calendar.",
        ) from e

    return AvailabilitySlotsResponse(
        slots=[
            {
                "start": slot.start,
                "end": slot.end,
                "timezone": slot.timezone,
                "display": slot.display,
            }
            for slot in slots
        ],
        checked_at=now,
        timezone=body.timezone,
        date_start=range_start,
        date_end=range_end,
        duration_minutes=body.duration_minutes,
        calendar_ids=calendar_ids,
        calendar_errors=calendar_errors,
    )


def _resolve_date_range(
    body: AvailabilitySlotRequest, now: datetime
) -> tuple[date, date]:
    """User-selected dates, or *days* from today in the request timezone (inclusive)."""
    if body.date_start is not None and body.date_end is not None:
        return body.date_start, body.date_end
    z = ZoneInfo(body.timezone)
    local_today = now.astimezone(z).date()
    d = int(body.days)
    return local_today, local_today + timedelta(days=d - 1)


def _resolve_calendar_account(
    db: Session, tenant_id: uuid.UUID, body: AvailabilitySlotRequest
) -> EmailAccount | None:
    if body.job_id:
        job = (
            db.query(Job)
            .filter(Job.id == body.job_id, Job.tenant_id == tenant_id)
            .first()
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        account = _resolve_account_for_job(db, tenant_id, body.job_id)
        if account:
            return account
    if body.account_id:
        return (
            db.query(EmailAccount)
            .filter(
                EmailAccount.id == body.account_id,
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


def _resolve_account_for_job(
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
    return None


def _calendar_auth_url(auth: AuthContext) -> str | None:
    if not settings.google_client_id or not settings.google_client_secret:
        return None
    state_token = create_access_token(
        {
            "sub": str(auth.user_id),
            "tenant_id": str(auth.tenant_id),
            "purpose": "calendar_oauth",
        }
    )
    return _build_google_auth_url(state_token, GOOGLE_CALENDAR_SCOPES)
