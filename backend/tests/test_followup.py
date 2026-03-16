"""Tests for follow-up email suggestion: detection, API, and generation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.email_account import EmailAccount
from app.models.job import Job, JobThread
from app.models.message import Message
from app.services.next_action import GHOSTED_DAYS


def _make_job(db_session, tenant_id, **kwargs) -> Job:
    job = Job(
        tenant_id=tenant_id,
        company=kwargs.get("company", "Acme"),
        role=kwargs.get("role", "SWE"),
        current_stage=kwargs.get("current_stage", "SOURCED"),
        last_activity=kwargs.get("last_activity"),
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_email_account(db_session, tenant_id, email_address="user@example.com") -> EmailAccount:
    from app.encryption import encrypt
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address=email_address,
        oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
    )
    db_session.add(account)
    db_session.commit()
    return account


def _make_message(db_session, tenant_id, account_id, *, from_address, thread_id=None, days_ago=0) -> Message:
    now = datetime.now(timezone.utc)
    msg = Message(
        tenant_id=tenant_id,
        account_id=account_id,
        provider_msg_id=f"msg-{now.timestamp()}",
        thread_id=thread_id,
        subject="Test",
        from_address=from_address,
        to_addresses=None,
        date_header=now - timedelta(days=days_ago),
        body_text="body",
        body_html=None,
        headers_json="{}",
        raw_payload_json="{}",
        label_ids_json=None,
    )
    db_session.add(msg)
    db_session.commit()
    return msg


def _link_thread(db_session, tenant_id, job: Job, thread_id: str) -> JobThread:
    jt = JobThread(
        tenant_id=tenant_id,
        job_id=job.id,
        thread_id=thread_id,
    )
    db_session.add(jt)
    db_session.commit()
    return jt


class TestFollowUpSuggestionApi:
    """POST /jobs/{id}/follow-up-suggestion."""

    def test_404_when_job_not_found(self, client, auth_header):
        r = client.get("/auth/me", headers=auth_header)
        fake_id = uuid.uuid4()
        resp = client.post(f"/jobs/{fake_id}/follow-up-suggestion", headers=auth_header)
        assert resp.status_code == 404

    def test_400_when_job_not_stalled(self, client, auth_header):
        from tests.conftest import TestSession
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        db_session = TestSession()
        job = _make_job(db_session, tenant_id, current_stage="APPLIED")
        resp = client.post(f"/jobs/{job.id}/follow-up-suggestion", headers=auth_header)
        assert resp.status_code == 400
        assert "stalled" in resp.json().get("detail", "").lower() or "not" in resp.json().get("detail", "").lower()

    @patch("app.routers.jobs.generate_followup_suggestion")
    def test_200_and_draft_when_stalled_and_llm_ok(
        self, mock_generate, client, auth_header
    ):
        from app.encryption import encrypt
        from app.models.llm_key import LlmKey
        from app.schemas.draft import DraftReplyResult

        from tests.conftest import TestSession

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])
        db_session = TestSession()

        account = _make_email_account(db_session, tenant_id, email_address="me@test.com")
        old_last_activity = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 1)
        job = _make_job(
            db_session,
            tenant_id,
            last_activity=old_last_activity,
            current_stage="INTERVIEW",
        )
        _link_thread(db_session, tenant_id, job, "thread-ghost")
        _make_message(
            db_session,
            tenant_id,
            account.id,
            from_address="recruiter@acme.com",
            thread_id="thread-ghost",
            days_ago=GHOSTED_DAYS + 1,
        )
        db_session.add(
            LlmKey(
                tenant_id=tenant_id,
                provider="openai",
                encrypted_key=encrypt("sk-fake"),
            )
        )
        db_session.commit()

        mock_generate.return_value = DraftReplyResult(
            subject="Re: SWE at Acme",
            body="Hi, following up on our conversation. I'm still very interested.",
            tone="professional",
            confidence=0.9,
        )

        resp = client.post(f"/jobs/{job.id}/follow-up-suggestion", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "Re: SWE at Acme"
        assert "following up" in data["body"].lower()
        assert data["draft"] is not None
        assert data["draft"]["job_id"] == str(job.id)
        assert data["draft"]["draft_type"] == "follow_up"
        assert data["draft"]["subject"] == "Re: SWE at Acme"

    def test_400_when_no_llm_key(self, client, auth_header):
        from tests.conftest import TestSession
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        db_session = TestSession()
        old_last_activity = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 1)
        job = _make_job(
            db_session,
            tenant_id,
            last_activity=old_last_activity,
            current_stage="INTERVIEW",
        )
        with patch("app.routers.jobs.generate_followup_suggestion") as mock_generate:
            mock_generate.side_effect = ValueError("LLM key not configured for this tenant")
            resp = client.post(f"/jobs/{job.id}/follow-up-suggestion", headers=auth_header)
        assert resp.status_code == 400
