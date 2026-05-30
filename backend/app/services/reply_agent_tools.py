"""Tool definitions and handlers for agentic reply draft generation."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.calendar_availability import fetch_availability_for_agent
from app.services.user_profile import get_or_create_profile, profile_dict_for_agent

REPLY_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": (
                "Get the job seeker's preferences: location, remote/hybrid/onsite, "
                "compensation expectations, preferred company sizes, timezone, and general availability notes."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_availability",
            "description": (
                "Fetch real free calendar slots from Google Calendar for proposing interview times. "
                "Use when the thread asks about scheduling or availability. "
                "If calendar is not connected, use profile availability_notes instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_start": {
                        "type": "string",
                        "description": "Start date YYYY-MM-DD (inclusive). Defaults to today in user timezone.",
                    },
                    "date_end": {
                        "type": "string",
                        "description": "End date YYYY-MM-DD (inclusive). Defaults to ~7 days from start.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Meeting length in minutes (default 30).",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone, e.g. America/New_York. Uses profile timezone if omitted.",
                    },
                },
                "required": [],
            },
        },
    },
]


def execute_reply_agent_tool(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    name: str,
    arguments_json: str,
    default_timezone: str | None,
) -> dict[str, Any]:
    if name == "get_user_profile":
        return _tool_get_user_profile(db, tenant_id, user_id)
    if name == "get_calendar_availability":
        args = json.loads(arguments_json or "{}")
        return _tool_get_calendar_availability(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            job_id=job_id,
            args=args,
            default_timezone=default_timezone,
        )
    return {"error": f"Unknown tool: {name}"}


def _tool_get_user_profile(
    db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, Any]:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == tenant_id)
        .first()
    )
    row = get_or_create_profile(db, user_id, tenant_id)
    return profile_dict_for_agent(row, user)


def _tool_get_calendar_availability(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    args: dict,
    default_timezone: str | None,
) -> dict[str, Any]:
    tz = (args.get("timezone") or default_timezone or "UTC").strip()
    duration = int(args.get("duration_minutes") or 30)
    date_start = _parse_ymd(args.get("date_start"))
    date_end = _parse_ymd(args.get("date_end"))
    return fetch_availability_for_agent(
        db,
        tenant_id=tenant_id,
        job_id=job_id,
        timezone_name=tz,
        date_start=date_start,
        date_end=date_end,
        duration_minutes=duration,
    )


def _parse_ymd(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
