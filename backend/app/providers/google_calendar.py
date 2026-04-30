"""Google Calendar availability helpers.

Uses the Calendar FreeBusy endpoint only; event titles/descriptions are never
fetched or stored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.models.email_account import EmailAccount
from app.providers.gmail import TokenRefreshError, _ensure_valid_token, _get_credentials

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
GOOGLE_CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"


class CalendarAuthError(Exception):
    """Raised when the account is not authorized for Calendar availability."""


@dataclass(frozen=True)
class BusyInterval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AvailabilitySlot:
    start: datetime
    end: datetime
    timezone: str
    display: str


def account_has_calendar_scope(account: EmailAccount) -> bool:
    """Return whether the encrypted OAuth blob says Calendar FreeBusy is granted."""
    try:
        creds = _get_credentials(account)
    except Exception:
        return False
    scopes = creds.get("scope") or creds.get("scopes") or ""
    if isinstance(scopes, list):
        scope_set = set(scopes)
    else:
        scope_set = set(str(scopes).split())
    return GOOGLE_CALENDAR_FREEBUSY_SCOPE in scope_set


class GoogleCalendarProvider:
    def __init__(self, db_session=None):
        self._db = db_session

    def fetch_busy_intervals(
        self,
        account: EmailAccount,
        *,
        time_min: datetime,
        time_max: datetime,
        calendar_ids: list[str],
        timezone_name: str,
    ) -> tuple[list[BusyInterval], dict[str, str]]:
        if not account_has_calendar_scope(account):
            raise CalendarAuthError("Calendar access is not connected for this account.")

        creds = _get_credentials(account)
        access_token = _ensure_valid_token(account, creds, self._db)
        body = {
            "timeMin": time_min.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": time_max.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeZone": timezone_name,
            "items": [{"id": cid} for cid in calendar_ids],
        }
        resp = httpx.post(
            GOOGLE_CALENDAR_FREEBUSY_URL,
            json=body,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if resp.status_code in (401, 403):
            raise CalendarAuthError("Calendar access was denied. Reconnect Calendar.")
        resp.raise_for_status()

        data = resp.json()
        intervals: list[BusyInterval] = []
        calendar_errors: dict[str, str] = {}
        for cal_id, cal_data in (data.get("calendars") or {}).items():
            errors = cal_data.get("errors") or []
            if errors:
                calendar_errors[cal_id] = "; ".join(
                    (err.get("reason") or err.get("domain") or "calendar_error")
                    for err in errors
                )
                continue
            for item in cal_data.get("busy") or []:
                start = _parse_google_datetime(item.get("start"))
                end = _parse_google_datetime(item.get("end"))
                if start and end and end > start:
                    intervals.append(BusyInterval(start=start, end=end))
        return intervals, calendar_errors


def compute_availability_slots(
    *,
    busy_intervals: list[BusyInterval],
    now: datetime,
    timezone_name: str,
    range_start_date: date,
    range_end_date: date,
    duration_minutes: int,
    workday_start: time,
    workday_end: time,
    slot_granularity_minutes: int,
    min_notice_minutes: int,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
    max_slots: int = 80,
) -> list[AvailabilitySlot]:
    """Subtract busy intervals from work windows and return selectable slots."""
    if range_end_date < range_start_date:
        return []

    tz = _load_timezone(timezone_name)
    local_now = now.astimezone(tz)
    earliest = local_now + timedelta(minutes=min_notice_minutes)
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=slot_granularity_minutes)
    buffer_before = timedelta(minutes=buffer_before_minutes)
    buffer_after = timedelta(minutes=buffer_after_minutes)

    expanded_busy = sorted(
        (
            BusyInterval(
                start=b.start.astimezone(tz) - buffer_before,
                end=b.end.astimezone(tz) + buffer_after,
            )
            for b in busy_intervals
        ),
        key=lambda b: b.start,
    )

    slots: list[AvailabilitySlot] = []
    d = range_start_date
    while d <= range_end_date:
        if d.weekday() < 5:
            window_start = datetime.combine(d, workday_start, tzinfo=tz)
            window_end = datetime.combine(d, workday_end, tzinfo=tz)
            if window_end > window_start:
                cursor = _round_up(max(window_start, earliest), step)
                for busy in expanded_busy:
                    if busy.end <= cursor or busy.start >= window_end:
                        continue
                    free_end = min(busy.start, window_end)
                    slots.extend(
                        _slots_in_gap(
                            cursor,
                            free_end,
                            duration=duration,
                            step=step,
                            timezone_name=timezone_name,
                            max_slots=max_slots - len(slots),
                        )
                    )
                    if len(slots) >= max_slots:
                        return slots
                    cursor = max(cursor, busy.end)
                    if cursor >= window_end:
                        break
                slots.extend(
                    _slots_in_gap(
                        cursor,
                        window_end,
                        duration=duration,
                        step=step,
                        timezone_name=timezone_name,
                        max_slots=max_slots - len(slots),
                    )
                )
                if len(slots) >= max_slots:
                    return slots
        d += timedelta(days=1)
    return slots


def _slots_in_gap(
    start: datetime,
    end: datetime,
    *,
    duration: timedelta,
    step: timedelta,
    timezone_name: str,
    max_slots: int,
) -> list[AvailabilitySlot]:
    slots: list[AvailabilitySlot] = []
    cursor = start
    while len(slots) < max_slots and cursor + duration <= end:
        slot_end = cursor + duration
        slots.append(
            AvailabilitySlot(
                start=cursor,
                end=slot_end,
                timezone=timezone_name,
                display=_format_slot(cursor, slot_end),
            )
        )
        cursor += step
    return slots


def _parse_google_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _round_up(dt: datetime, step: timedelta) -> datetime:
    seconds = int(step.total_seconds())
    if seconds <= 0:
        return dt
    timestamp = int(dt.timestamp())
    rounded = ((timestamp + seconds - 1) // seconds) * seconds
    return datetime.fromtimestamp(rounded, tz=dt.tzinfo)


def _load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"Unknown timezone: {timezone_name}") from e


def _format_slot(start: datetime, end: datetime) -> str:
    same_day = start.date() == end.date()
    date_part = f"{start.strftime('%a')}, {start.strftime('%b')} {start.day}"
    start_part = _format_time(start)
    end_part = _format_time(end) if same_day else f"{end.strftime('%a')}, {end.strftime('%b')} {end.day}, {_format_time(end)}"
    tz_name = start.tzname() or ""
    return f"{date_part}, {start_part}-{end_part} {tz_name}".strip()


def _format_time(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
