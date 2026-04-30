from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.email_account import EmailAccount
from app.models.job import Job, JobThread
from app.models.message import Message
from app.services.next_action import (
    GHOSTED_DAYS,
    NEEDS_REPLY_DAYS,
    compute_next_actions_for_jobs,
    suggest_followup_for_next_action,
)
from app.services.next_action import NextActionData


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
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address=email_address,
        oauth_encrypted="dummy",
    )
    db_session.add(account)
    db_session.commit()
    return account


def _make_message(
    db_session,
    tenant_id,
    account_id,
    *,
    from_address,
    thread_id=None,
    days_ago=0,
) -> Message:
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


class TestNextActionRules:
    def test_needs_reply_when_last_from_recruiter_recent(
        self, client, auth_header
    ):
        # Arrange: tenant + job + owner account
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        job = _make_job(db_session, tenant_id)
        account = _make_email_account(db_session, tenant_id, email_address="me@test.com")

        # Last message from recruiter yesterday
        _make_message(
            db_session,
            tenant_id,
            account.id,
            from_address="Recruiter <recruiter@company.com>",
            thread_id="thread-1",
            days_ago=1,
        )

        _link_thread(db_session, tenant_id, job, "thread-1")

        # Act
        actions = compute_next_actions_for_jobs(db_session, tenant_id, [job])
        action = actions[job.id]

        # Assert
        assert action is not None
        assert action.type == "needs_reply"
        assert "replied" in action.label.lower()

        msg = (
            db_session.query(Message)
            .filter(Message.tenant_id == tenant_id, Message.thread_id == "thread-1")
            .order_by(Message.date_header.desc())
            .first()
        )
        actions_dismissed = compute_next_actions_for_jobs(
            db_session,
            tenant_id,
            [job],
            needs_reply_dismissed_message_by_job={job.id: msg.id},
        )
        assert actions_dismissed[job.id] is None

    def test_follow_up_when_last_from_recruiter_old(
        self, client, auth_header
    ):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        job = _make_job(db_session, tenant_id)
        account = _make_email_account(db_session, tenant_id, email_address="me@test.com")

        # Last message from recruiter NEEDS_REPLY_DAYS days ago
        _make_message(
            db_session,
            tenant_id,
            account.id,
            from_address="Recruiter <recruiter@company.com>",
            thread_id="thread-1",
            days_ago=NEEDS_REPLY_DAYS,
        )

        _link_thread(db_session, tenant_id, job, "thread-1")

        actions = compute_next_actions_for_jobs(db_session, tenant_id, [job])
        action = actions[job.id]

        assert action is not None
        assert action.type == "follow_up"
        assert "follow up" in action.label.lower()

        msg = (
            db_session.query(Message)
            .filter(Message.tenant_id == tenant_id, Message.thread_id == "thread-1")
            .order_by(Message.date_header.desc())
            .first()
        )
        out = compute_next_actions_for_jobs(
            db_session,
            tenant_id,
            [job],
            needs_reply_dismissed_message_by_job={job.id: msg.id},
        )
        assert out[job.id] is None

    def test_dismiss_falls_through_to_ghosted(
        self, client, auth_header
    ):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        old = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 1)
        job = _make_job(
            db_session,
            tenant_id,
            last_activity=old,
            current_stage="INTERVIEW",
        )
        account = _make_email_account(db_session, tenant_id, email_address="me@test.com")
        m = _make_message(
            db_session,
            tenant_id,
            account.id,
            from_address="Recruiter <recruiter@company.com>",
            thread_id="thread-ghost",
            days_ago=1,
        )
        _link_thread(db_session, tenant_id, job, "thread-ghost")
        a1 = compute_next_actions_for_jobs(db_session, tenant_id, [job])
        assert a1[job.id] is not None
        assert a1[job.id].type == "needs_reply"
        a2 = compute_next_actions_for_jobs(
            db_session,
            tenant_id,
            [job],
            needs_reply_dismissed_message_by_job={job.id: m.id},
        )
        assert a2[job.id] is not None
        assert a2[job.id].type == "ghosted"

    def test_no_action_when_last_from_owner(
        self, client, auth_header
    ):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        job = _make_job(db_session, tenant_id)
        account = _make_email_account(db_session, tenant_id, email_address="me@test.com")

        # Last message from owner, not recruiter
        _make_message(
            db_session,
            tenant_id,
            account.id,
            from_address="Me <me@test.com>",
            thread_id="thread-1",
            days_ago=1,
        )

        actions = compute_next_actions_for_jobs(db_session, tenant_id, [job])
        action = actions[job.id]

        assert action is None

    def test_ghosted_when_no_activity_for_many_days(
        self, client, auth_header
    ):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        # Job with old last_activity and no messages
        from tests.conftest import TestSession

        db_session = TestSession()
        old_last_activity = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 1)
        job = _make_job(
            db_session,
            tenant_id,
            last_activity=old_last_activity,
            current_stage="INTERVIEW",
        )

        actions = compute_next_actions_for_jobs(db_session, tenant_id, [job])
        action = actions[job.id]

        assert action is not None
        assert action.type == "ghosted"
        assert "ghosted" in action.label.lower()

    def test_no_action_for_terminal_stages(
        self, client, auth_header
    ):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        old_last_activity = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 30)
        for stage in ("REJECTED", "WITHDRAWN"):
            job = _make_job(
                db_session,
                tenant_id,
                last_activity=old_last_activity,
                current_stage=stage,
            )

            actions = compute_next_actions_for_jobs(db_session, tenant_id, [job])
            action = actions[job.id]
            assert action is None

    def test_suggest_followup_true_for_follow_up_and_ghosted(self):
        assert suggest_followup_for_next_action(
            NextActionData(type="follow_up", label="Follow up with recruiter")
        ) is True
        assert suggest_followup_for_next_action(
            NextActionData(type="ghosted", label="Ghosted?")
        ) is True

    def test_suggest_followup_false_for_needs_reply_and_none(self):
        assert suggest_followup_for_next_action(
            NextActionData(type="needs_reply", label="You haven't replied yet")
        ) is False
        assert suggest_followup_for_next_action(None) is False


class TestNextActionApiIntegration:
    def test_job_list_includes_next_action_field(
        self, client, auth_header
    ):
        # Create a job without any messages; next_action should be null but field present.
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        _make_job(db_session, tenant_id)

        resp = client.get("/jobs", headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert "next_action" in body["items"][0]
        assert "suggest_followup" in body["items"][0]
        assert body["items"][0]["suggest_followup"] is False

    def test_timeline_includes_next_action_on_job(
        self, client, auth_header
    ):
        # Create a job that should be ghosted so next_action is non-null on timeline.job
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        from tests.conftest import TestSession

        db_session = TestSession()
        old_last_activity = datetime.now(timezone.utc) - timedelta(days=GHOSTED_DAYS + 1)
        job = _make_job(
            db_session,
            tenant_id,
            last_activity=old_last_activity,
            current_stage="INTERVIEW",
        )

        resp = client.get(f"/jobs/{job.id}/timeline", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job"]["id"] == str(job.id)
        assert data["job"]["next_action"] is not None
        assert data["job"]["next_action"]["type"] == "ghosted"
        assert data["job"]["suggest_followup"] is True

