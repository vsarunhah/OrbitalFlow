import json
import uuid
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.providers.google_calendar import BusyInterval, compute_availability_slots


def test_compute_availability_filters_by_duration_and_busy_blocks():
    tz = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 4, 27, 8, 0, tzinfo=tz)
    busy = [
        BusyInterval(
            start=datetime(2026, 4, 27, 10, 0, tzinfo=tz),
            end=datetime(2026, 4, 27, 11, 0, tzinfo=tz),
        ),
        BusyInterval(
            start=datetime(2026, 4, 27, 15, 30, tzinfo=tz),
            end=datetime(2026, 4, 27, 16, 30, tzinfo=tz),
        ),
    ]

    slots = compute_availability_slots(
        busy_intervals=busy,
        now=now,
        timezone_name="America/Los_Angeles",
        range_start_date=date(2026, 4, 27),
        range_end_date=date(2026, 4, 27),
        duration_minutes=60,
        workday_start=time(9, 0),
        workday_end=time(17, 0),
        slot_granularity_minutes=30,
        min_notice_minutes=0,
    )

    starts = [slot.start.strftime("%H:%M") for slot in slots]
    assert "09:00" in starts
    assert "09:30" not in starts
    assert "10:00" not in starts
    assert "14:30" in starts
    assert "15:00" not in starts
    assert "16:30" not in starts


def test_availability_endpoint_returns_connect_required_for_missing_scope(client, auth_header):
    from tests.conftest import TestSession

    me = client.get("/auth/me", headers=auth_header).json()
    tenant_id = uuid.UUID(me["tenant_id"])
    db = TestSession()
    try:
        account = EmailAccount(
            tenant_id=tenant_id,
            email_address="me@test.com",
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x", "scopes": "openid email"})),
            status="active",
        )
        db.add(account)
        db.commit()
        account_id = account.id
    finally:
        db.close()

    resp = client.post(
        "/calendar/availability/slots",
        headers=auth_header,
        json={
            "account_id": str(account_id),
            "duration_minutes": 30,
            "timezone": "America/Los_Angeles",
            "date_start": "2026-04-20",
            "date_end": "2026-04-25",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["slots"] == []
    assert data["connect_required"]["required"] is True
    assert data["date_start"] == "2026-04-20"
    assert data["date_end"] == "2026-04-25"
