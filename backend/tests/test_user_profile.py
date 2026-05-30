"""Tests for job-seeker profile API and agent helpers."""

from __future__ import annotations

import uuid

from app.models.user import User
from app.services.reply_agent_tools import execute_reply_agent_tool
from app.services.user_profile import get_or_create_profile, profile_dict_for_agent


def test_get_profile_creates_empty(client, auth_header):
    r = client.get("/user/profile", headers=auth_header)
    assert r.status_code == 200
    data = r.json()
    assert data["preferred_company_sizes"] == []
    assert data["work_arrangements"] == []
    assert data["compensation_expectations"] is None


def test_patch_profile(client, auth_header):
    r = client.patch(
        "/user/profile",
        headers=auth_header,
        json={
            "display_name": "Alex",
            "timezone": "America/New_York",
            "location_preferences": "Remote US; open to NYC hybrid monthly",
            "work_arrangements": ["remote", "hybrid", "invalid"],
            "compensation_expectations": "$200k+ base",
            "preferred_company_sizes": ["startup", "mid", "invalid"],
            "availability_notes": "Prefer mornings ET",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["display_name"] == "Alex"
    assert data["work_arrangements"] == ["remote", "hybrid"]
    assert data["preferred_company_sizes"] == ["startup", "mid"]
    assert data["compensation_expectations"] == "$200k+ base"


def test_profile_tool_returns_configured():
    from tests.conftest import TestSession
    from app.models.tenant import Tenant

    db_session = TestSession()
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email="seeker@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.flush()
    row = get_or_create_profile(db_session, user.id, tenant.id)
    row.compensation_expectations = "$180k"
    row.preferred_company_sizes = ["large"]
    db_session.commit()

    result = execute_reply_agent_tool(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        job_id=uuid.uuid4(),
        name="get_user_profile",
        arguments_json="{}",
        default_timezone=None,
    )
    assert result["configured"] is True
    assert result["compensation_expectations"] == "$180k"
    assert result["preferred_company_sizes"] == ["large"]
    db_session.close()
