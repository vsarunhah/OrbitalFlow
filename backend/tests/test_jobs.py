"""Tests for Phase 6: Jobs + reducer + timeline.

Covers:
  - Deterministic stage reducer rules
  - Manual override endpoint + audit logging
  - Job list / detail / timeline endpoints
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.encryption import encrypt
from app.models.draft import MessageDraft, SentMessage
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.schemas.extraction import EventType
from app.schemas.job import CONFIDENCE_THRESHOLD, JobStage
from app.services.stage_reducer import compute_new_stage


# =====================================================================
# Stage reducer (pure unit tests — no DB)
# =====================================================================


class TestStageReducer:
    """Verify every rule from SPEC.md."""

    def test_application_received_to_applied(self):
        result = compute_new_stage(JobStage.SOURCED, EventType.APPLICATION_RECEIVED.value, 0.95)
        assert result == JobStage.APPLIED

    def test_interview_request_to_interview(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.INTERVIEW_REQUEST.value, 0.90)
        assert result == JobStage.INTERVIEW

    def test_interview_scheduled_to_interview(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.INTERVIEW_SCHEDULED.value, 0.85)
        assert result == JobStage.INTERVIEW

    def test_interview_reschedule_to_interview(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.INTERVIEW_RESCHEDULE.value, 0.80)
        assert result == JobStage.INTERVIEW

    def test_takehome_request_to_takehome(self):
        result = compute_new_stage(JobStage.INTERVIEW, EventType.TAKEHOME_REQUEST.value, 0.90)
        assert result == JobStage.TAKEHOME

    def test_offer_to_offer(self):
        result = compute_new_stage(JobStage.INTERVIEW, EventType.OFFER.value, 0.95)
        assert result == JobStage.OFFER

    def test_rejection_to_rejected(self):
        result = compute_new_stage(JobStage.INTERVIEW, EventType.REJECTION.value, 0.95)
        assert result == JobStage.REJECTED

    def test_rejection_from_any_non_terminal_stage(self):
        for stage in (JobStage.SOURCED, JobStage.APPLIED, JobStage.SCREEN,
                      JobStage.INTERVIEW, JobStage.TAKEHOME, JobStage.FINAL, JobStage.OFFER):
            result = compute_new_stage(stage, EventType.REJECTION.value, 0.95)
            assert result == JobStage.REJECTED, f"REJECTION should reach REJECTED from {stage}"

    # --- Never auto-downgrade ---

    def test_no_downgrade_interview_to_applied(self):
        result = compute_new_stage(JobStage.INTERVIEW, EventType.APPLICATION_RECEIVED.value, 0.95)
        assert result is None

    def test_no_downgrade_offer_to_interview(self):
        result = compute_new_stage(JobStage.OFFER, EventType.INTERVIEW_REQUEST.value, 0.95)
        assert result is None

    def test_no_downgrade_takehome_to_applied(self):
        result = compute_new_stage(JobStage.TAKEHOME, EventType.APPLICATION_RECEIVED.value, 0.95)
        assert result is None

    def test_same_stage_no_change(self):
        result = compute_new_stage(JobStage.INTERVIEW, EventType.INTERVIEW_REQUEST.value, 0.95)
        assert result is None

    # --- Never auto-change out of terminal stages ---

    def test_no_exit_rejected(self):
        for evt in EventType:
            result = compute_new_stage(JobStage.REJECTED, evt.value, 1.0)
            assert result is None, f"Should not auto-exit REJECTED for {evt}"

    def test_no_exit_withdrawn(self):
        for evt in EventType:
            result = compute_new_stage(JobStage.WITHDRAWN, evt.value, 1.0)
            assert result is None, f"Should not auto-exit WITHDRAWN for {evt}"

    # --- Confidence threshold ---

    def test_below_threshold_no_change(self):
        result = compute_new_stage(
            JobStage.SOURCED,
            EventType.APPLICATION_RECEIVED.value,
            CONFIDENCE_THRESHOLD - 0.01,
        )
        assert result is None

    def test_at_threshold_changes(self):
        result = compute_new_stage(
            JobStage.SOURCED,
            EventType.APPLICATION_RECEIVED.value,
            CONFIDENCE_THRESHOLD,
        )
        assert result == JobStage.APPLIED

    # --- Unmapped event types produce no change ---

    def test_follow_up_no_change(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.FOLLOW_UP.value, 0.95)
        assert result is None

    def test_job_alert_no_change(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.JOB_ALERT.value, 0.95)
        assert result is None

    def test_none_event_no_change(self):
        result = compute_new_stage(JobStage.APPLIED, EventType.NONE.value, 0.95)
        assert result is None


# =====================================================================
# API endpoint tests (require DB + auth)
# =====================================================================


def _create_job_in_db(client, auth_header, db_session, *, stage="SOURCED", company="Acme", role="SWE"):
    """Helper: insert a Job row directly, return its id."""
    from app.models.job import Job as JobModel

    r = client.get("/auth/me", headers=auth_header)
    tenant_id = uuid.UUID(r.json()["tenant_id"])

    job = JobModel(
        tenant_id=tenant_id,
        company=company,
        role=role,
        current_stage=stage,
    )
    db_session.add(job)
    db_session.commit()
    return job.id, tenant_id


@pytest.fixture()
def db_session():
    """Provide a raw DB session matching the test override."""
    from tests.conftest import TestSession
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


class TestJobEndpoints:
    def test_list_jobs_empty(self, client, auth_header):
        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_list_jobs_returns_created(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session)
        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1
        assert body["total"] == 1
        assert body["items"][0]["company"] == "Acme"
        assert body["items"][0]["current_stage"] == "SOURCED"
        assert body["items"][0]["unread_incoming_count"] == 0

    def test_unread_incoming_count_after_new_recruiter_message(
        self, client, auth_header, db_session
    ):
        """A never-opened job with inbound is unread; opening resets; new inbound re-arms it."""
        from datetime import datetime, timedelta, timezone

        from app.models.job import JobEvent

        job_id, tenant_id = _create_job_in_db(client, auth_header, db_session)
        me = client.get("/auth/me", headers=auth_header).json()
        user_email = me["email"]

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address=user_email,
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
        )
        db_session.add(account)
        db_session.flush()

        m1 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="m-unread-1",
            raw_payload_json="{}",
            from_address="Recruiter <recruiter@acme.com>",
            date_header=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(m1)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=job_id,
                message_id=m1.id,
                source="extraction",
            )
        )
        db_session.commit()

        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["items"][0]["unread_incoming_count"] == 1

        tr = client.get(f"/jobs/{job_id}/timeline", headers=auth_header)
        assert tr.status_code == 200

        after_open = client.get("/jobs", headers=auth_header).json()
        assert after_open["items"][0]["unread_incoming_count"] == 0

        future = datetime.now(timezone.utc) + timedelta(hours=2)
        m2 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="m-unread-2",
            raw_payload_json="{}",
            from_address="Recruiter <recruiter@acme.com>",
            date_header=future,
        )
        db_session.add(m2)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=job_id,
                message_id=m2.id,
                source="extraction",
            )
        )
        db_session.commit()

        r2 = client.get("/jobs", headers=auth_header)
        assert r2.status_code == 200
        assert r2.json()["items"][0]["unread_incoming_count"] == 1

    def test_list_jobs_unread_only(self, client, auth_header, db_session):
        """unread_only=true returns only jobs with unread_incoming_count > 0."""
        from datetime import datetime, timedelta, timezone

        from app.models.job import Job, JobEvent

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_email = r.json()["email"]

        quiet = Job(tenant_id=tenant_id, company="Quiet", role="A", current_stage="SOURCED")
        noisy = Job(tenant_id=tenant_id, company="Noisy", role="B", current_stage="SOURCED")
        db_session.add_all([quiet, noisy])
        db_session.flush()

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address=user_email,
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
        )
        db_session.add(account)
        db_session.flush()

        m0 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="m-quiet",
            raw_payload_json="{}",
            from_address="R <r@x.com>",
            date_header=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(m0)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=quiet.id,
                message_id=m0.id,
                source="extraction",
            )
        )

        m1 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="m-noisy-1",
            raw_payload_json="{}",
            from_address="R <r@y.com>",
            date_header=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(m1)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=noisy.id,
                message_id=m1.id,
                source="extraction",
            )
        )
        db_session.commit()

        client.get(f"/jobs/{quiet.id}/timeline", headers=auth_header)
        client.get(f"/jobs/{noisy.id}/timeline", headers=auth_header)

        future = datetime.now(timezone.utc) + timedelta(hours=3)
        m2 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="m-noisy-2",
            raw_payload_json="{}",
            from_address="R <r@y.com>",
            date_header=future,
        )
        db_session.add(m2)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=noisy.id,
                message_id=m2.id,
                source="extraction",
            )
        )
        db_session.commit()

        resp = client.get("/jobs", params={"unread_only": True}, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["company"] == "Noisy"

    def test_timeline_read_mark_unread_endpoint(self, client, auth_header, db_session):
        from datetime import datetime, timedelta, timezone

        from app.models.job import JobEvent

        job_id, tenant_id = _create_job_in_db(client, auth_header, db_session)
        me = client.get("/auth/me", headers=auth_header).json()
        user_email = me["email"]

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address=user_email,
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
        )
        db_session.add(account)
        db_session.flush()

        m1 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="mu-1",
            raw_payload_json="{}",
            from_address="Recruiter <rec@acme.com>",
            date_header=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(m1)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=job_id,
                message_id=m1.id,
                source="extraction",
            )
        )
        db_session.commit()

        client.get(f"/jobs/{job_id}/timeline", headers=auth_header)
        caught_up = client.get("/jobs", headers=auth_header).json()
        assert caught_up["items"][0]["unread_incoming_count"] == 0

        mu = client.post(
            f"/jobs/{job_id}/timeline-read",
            headers=auth_header,
            json={"read": False},
        )
        assert mu.status_code == 200
        assert mu.json()["unread_incoming_count"] >= 1

        mr = client.post(
            f"/jobs/{job_id}/timeline-read",
            headers=auth_header,
            json={"read": True},
        )
        assert mr.status_code == 200
        assert mr.json()["unread_incoming_count"] == 0

    def test_dismiss_needs_reply_endpoint(self, client, auth_header, db_session):
        from datetime import datetime, timedelta, timezone

        from app.models.job import JobEvent, JobThread

        job_id, tenant_id = _create_job_in_db(client, auth_header, db_session)
        me = client.get("/auth/me", headers=auth_header).json()
        user_email = me["email"]

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address=user_email,
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
        )
        db_session.add(account)
        db_session.flush()
        m1 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="dismiss-nr-1",
            raw_payload_json="{}",
            from_address="Recruiter <recruiter@acme.com>",
            date_header=datetime.now(timezone.utc) - timedelta(hours=1),
            thread_id="dismiss-t1",
        )
        db_session.add(m1)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=job_id,
                message_id=m1.id,
                source="extraction",
            )
        )
        db_session.add(
            JobThread(tenant_id=tenant_id, job_id=job_id, thread_id="dismiss-t1")
        )
        db_session.commit()

        det = client.get(f"/jobs/{job_id}", headers=auth_header)
        assert det.status_code == 200
        assert det.json()["next_action"] is not None
        dis = client.post(
            f"/jobs/{job_id}/dismiss-needs-reply",
            headers=auth_header,
        )
        assert dis.status_code == 200
        assert dis.json()["next_action"] is None

    def test_dismiss_needs_reply_400_when_no_inbound(
        self, client, auth_header, db_session
    ):
        from datetime import datetime, timedelta, timezone

        from app.models.job import JobEvent, JobThread

        job_id, tenant_id = _create_job_in_db(client, auth_header, db_session)
        me = client.get("/auth/me", headers=auth_header).json()
        user_email = me["email"]
        account = EmailAccount(
            tenant_id=tenant_id,
            email_address=user_email,
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
        )
        db_session.add(account)
        db_session.flush()
        m1 = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="dismiss-nr-2",
            raw_payload_json="{}",
            from_address=f"Me <{user_email}>",
            date_header=datetime.now(timezone.utc) - timedelta(hours=1),
            thread_id="dismiss-t2",
        )
        db_session.add(m1)
        db_session.flush()
        db_session.add(
            JobEvent(
                tenant_id=tenant_id,
                job_id=job_id,
                message_id=m1.id,
                source="extraction",
            )
        )
        db_session.add(
            JobThread(tenant_id=tenant_id, job_id=job_id, thread_id="dismiss-t2")
        )
        db_session.commit()

        dis = client.post(
            f"/jobs/{job_id}/dismiss-needs-reply",
            headers=auth_header,
        )
        assert dis.status_code == 400

    def test_list_jobs_sorted_by_updated_at_desc(self, client, auth_header, db_session):
        """Job list defaults to most recently updated job rows (cheap indexed sort)."""
        from datetime import datetime, timedelta, timezone

        from app.models.job import Job as JobRow

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        older = JobRow(tenant_id=tenant_id, company="Older", role="A", current_stage="SOURCED")
        newer = JobRow(tenant_id=tenant_id, company="Newer", role="B", current_stage="SOURCED")
        db_session.add_all([older, newer])
        db_session.flush()

        now = datetime.now(timezone.utc)
        older.updated_at = now - timedelta(days=2)
        newer.updated_at = now - timedelta(days=1)
        db_session.commit()

        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        assert [j["company"] for j in r.json()["items"]] == ["Newer", "Older"]

    def test_get_job_detail(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session)
        r = client.get(f"/jobs/{job_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["id"] == str(job_id)

    def test_get_job_not_found(self, client, auth_header):
        r = client.get(f"/jobs/{uuid.uuid4()}", headers=auth_header)
        assert r.status_code == 404

    def test_timeline_empty(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session)
        r = client.get(f"/jobs/{job_id}/timeline", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["job"]["id"] == str(job_id)
        assert data["events"] == []
        assert data["messages"] == []


class TestManualOverride:
    def test_manual_stage_change(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session)

        r = client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "APPLIED", "reason": "User applied manually"},
        )
        assert r.status_code == 200
        assert r.json()["current_stage"] == "APPLIED"

    def test_manual_override_logged_in_stage_history(self, client, auth_header, db_session):
        from app.models.job import JobStageHistory

        job_id, tenant_id = _create_job_in_db(client, auth_header, db_session)

        client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "INTERVIEW", "reason": "Scheduled by recruiter"},
        )

        rows = db_session.query(JobStageHistory).filter(
            JobStageHistory.job_id == job_id
        ).all()
        assert len(rows) == 1
        assert rows[0].stage_before == "SOURCED"
        assert rows[0].stage_after == "INTERVIEW"
        assert rows[0].source == "manual"
        assert rows[0].rationale == "Scheduled by recruiter"

    def test_manual_override_logged_in_manual_changes(self, client, auth_header, db_session):
        from app.models.job import JobManualChange

        job_id, _ = _create_job_in_db(client, auth_header, db_session)

        client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "WITHDRAWN", "reason": "Changed my mind"},
        )

        rows = db_session.query(JobManualChange).filter(
            JobManualChange.job_id == job_id
        ).all()
        assert len(rows) == 1
        assert rows[0].stage_before == "SOURCED"
        assert rows[0].stage_after == "WITHDRAWN"
        assert rows[0].reason == "Changed my mind"

    def test_manual_override_creates_timeline_event(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session)

        client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "REJECTED", "reason": "Got rejection call"},
        )

        r = client.get(f"/jobs/{job_id}/timeline", headers=auth_header)
        events = r.json()["events"]
        assert len(events) == 1
        assert events[0]["source"] == "manual"
        assert events[0]["stage_before"] == "SOURCED"
        assert events[0]["stage_after"] == "REJECTED"

    def test_manual_override_can_exit_rejected(self, client, auth_header, db_session):
        """Manual override should allow leaving terminal stages."""
        job_id, _ = _create_job_in_db(client, auth_header, db_session, stage="REJECTED")

        r = client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "INTERVIEW", "reason": "Recruiter reconsidered"},
        )
        assert r.status_code == 200
        assert r.json()["current_stage"] == "INTERVIEW"

    def test_manual_override_can_downgrade(self, client, auth_header, db_session):
        """Manual override allows going to a lower stage."""
        job_id, _ = _create_job_in_db(client, auth_header, db_session, stage="OFFER")

        r = client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "APPLIED", "reason": "Misclassified"},
        )
        assert r.status_code == 200
        assert r.json()["current_stage"] == "APPLIED"

    def test_manual_override_same_stage_rejected(self, client, auth_header, db_session):
        job_id, _ = _create_job_in_db(client, auth_header, db_session, stage="APPLIED")

        r = client.post(
            f"/jobs/{job_id}/stage",
            headers=auth_header,
            json={"new_stage": "APPLIED", "reason": "no-op"},
        )
        assert r.status_code == 400

    def test_manual_override_not_found(self, client, auth_header):
        r = client.post(
            f"/jobs/{uuid.uuid4()}/stage",
            headers=auth_header,
            json={"new_stage": "APPLIED", "reason": "test"},
        )
        assert r.status_code == 404

    def test_merge_jobs(self, client, auth_header, db_session):
        """Manual merge: source jobs are merged into target and removed."""
        target_id, _ = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="SWE"
        )
        source_id, _ = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="Software Engineer"
        )

        r = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={
                "target_job_id": str(target_id),
                "source_job_ids": [str(source_id)],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["merged_job_id"] == str(target_id)
        assert body["removed_job_ids"] == [str(source_id)]
        assert body["status"] == "merged"

        r = client.get("/jobs", headers=auth_header)
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["id"] == str(target_id)

    def test_merge_jobs_repoints_drafts_and_sent_messages(
        self, client, auth_header, db_session
    ):
        """Merge succeeds and message_drafts/sent_messages are re-pointed to target job."""
        target_id, tenant_id = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="SWE"
        )
        source_id, _ = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="Software Engineer"
        )

        r = client.get("/auth/me", headers=auth_header)
        user_id = uuid.UUID(r.json()["user_id"])

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address="me@test.com",
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
        )
        db_session.add(account)
        db_session.flush()

        draft = MessageDraft(
            tenant_id=tenant_id,
            job_id=source_id,
            account_id=account.id,
            subject="Re: Role",
            body_text="Interested",
            status="GENERATED",
            created_by_user_id=user_id,
        )
        db_session.add(draft)
        sent = SentMessage(
            tenant_id=tenant_id,
            job_id=source_id,
            account_id=account.id,
            provider="gmail",
            to_addrs_json='["recruiter@acme.com"]',
            subject="Re: Follow up",
            body_text="Thank you.",
        )
        db_session.add(sent)
        db_session.commit()

        merge_resp = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={
                "target_job_id": str(target_id),
                "source_job_ids": [str(source_id)],
            },
        )
        assert merge_resp.status_code == 200
        assert merge_resp.json()["status"] == "merged"

        db_session.expire_all()
        drafts_for_target = db_session.query(MessageDraft).filter(
            MessageDraft.job_id == target_id
        ).all()
        drafts_for_source = db_session.query(MessageDraft).filter(
            MessageDraft.job_id == source_id
        ).all()
        sent_for_target = db_session.query(SentMessage).filter(
            SentMessage.job_id == target_id
        ).all()
        sent_for_source = db_session.query(SentMessage).filter(
            SentMessage.job_id == source_id
        ).all()

        assert len(drafts_for_target) == 1
        assert drafts_for_target[0].subject == "Re: Role"
        assert len(drafts_for_source) == 0
        assert len(sent_for_target) == 1
        assert sent_for_target[0].subject == "Re: Follow up"
        assert len(sent_for_source) == 0

    def test_merge_jobs_repoints_manual_change_history(
        self, client, auth_header, db_session
    ):
        """Merge moves job_manual_changes from source to target so delete succeeds."""
        from app.models.job import JobManualChange

        target_id, tenant_id = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="SWE"
        )
        source_id, _ = _create_job_in_db(
            client, auth_header, db_session, company="Acme", role="Software Engineer"
        )

        r = client.get("/auth/me", headers=auth_header)
        user_id = uuid.UUID(r.json()["user_id"])

        entry = JobManualChange(
            tenant_id=tenant_id,
            job_id=source_id,
            user_id=user_id,
            stage_before="APPLIED",
            stage_after="INTERVIEW",
            reason="User corrected pipeline",
        )
        db_session.add(entry)
        db_session.commit()

        merge_resp = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={
                "target_job_id": str(target_id),
                "source_job_ids": [str(source_id)],
            },
        )
        assert merge_resp.status_code == 200
        assert merge_resp.json()["status"] == "merged"

        db_session.expire_all()
        for_source = db_session.query(JobManualChange).filter(
            JobManualChange.job_id == source_id
        ).all()
        for_target = db_session.query(JobManualChange).filter(
            JobManualChange.job_id == target_id
        ).all()

        assert len(for_source) == 0
        assert len(for_target) == 1
        assert for_target[0].reason == "User corrected pipeline"
        assert for_target[0].stage_before == "APPLIED"
        assert for_target[0].stage_after == "INTERVIEW"

    def test_merge_takes_min_last_seen_and_none_dominates(
        self, client, auth_header, db_session
    ):
        """Merging must preserve unread: per user take min(last_seen_at); a never-opened side wins."""
        from datetime import datetime, timedelta, timezone

        from app.models.job import JobTimelineReadState

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        # --- Case 1: both opened. Target row should end up at the earlier of the two. ---
        target_a, _ = _create_job_in_db(
            client, auth_header, db_session, company="A", role="t"
        )
        source_a, _ = _create_job_in_db(
            client, auth_header, db_session, company="A", role="s"
        )
        earlier = datetime.now(timezone.utc) - timedelta(days=2)
        later = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.add(
            JobTimelineReadState(
                tenant_id=tenant_id, user_id=user_id, job_id=source_a, last_seen_at=earlier
            )
        )
        db_session.add(
            JobTimelineReadState(
                tenant_id=tenant_id, user_id=user_id, job_id=target_a, last_seen_at=later
            )
        )
        db_session.commit()

        resp_a = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={"target_job_id": str(target_a), "source_job_ids": [str(source_a)]},
        )
        assert resp_a.status_code == 200

        db_session.expire_all()
        rows_a = db_session.query(JobTimelineReadState).filter(
            JobTimelineReadState.job_id == target_a
        ).all()
        assert len(rows_a) == 1
        got_a = rows_a[0].last_seen_at
        if got_a.tzinfo is None:
            got_a = got_a.replace(tzinfo=timezone.utc)
        assert abs((got_a - earlier).total_seconds()) < 1

        # --- Case 2: only target opened. Result must be "never opened" (row deleted). ---
        target_b, _ = _create_job_in_db(
            client, auth_header, db_session, company="B", role="t"
        )
        source_b, _ = _create_job_in_db(
            client, auth_header, db_session, company="B", role="s"
        )
        db_session.add(
            JobTimelineReadState(
                tenant_id=tenant_id, user_id=user_id, job_id=target_b,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        resp_b = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={"target_job_id": str(target_b), "source_job_ids": [str(source_b)]},
        )
        assert resp_b.status_code == 200

        db_session.expire_all()
        rows_b = db_session.query(JobTimelineReadState).filter(
            JobTimelineReadState.job_id == target_b
        ).all()
        assert rows_b == []

        # --- Case 3: only source opened. Cascade drops source's row; target stays row-less. ---
        target_c, _ = _create_job_in_db(
            client, auth_header, db_session, company="C", role="t"
        )
        source_c, _ = _create_job_in_db(
            client, auth_header, db_session, company="C", role="s"
        )
        db_session.add(
            JobTimelineReadState(
                tenant_id=tenant_id, user_id=user_id, job_id=source_c,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        resp_c = client.post(
            "/jobs/merge",
            headers=auth_header,
            json={"target_job_id": str(target_c), "source_job_ids": [str(source_c)]},
        )
        assert resp_c.status_code == 200

        db_session.expire_all()
        rows_c = db_session.query(JobTimelineReadState).filter(
            JobTimelineReadState.job_id == target_c
        ).all()
        assert rows_c == []


class TestJobContactDeduplication:
    """Regression: same contact in extraction twice (e.g. different roles) must not duplicate job_contacts."""

    def test_duplicate_contact_in_extraction_creates_single_job_contact(
        self, client, auth_header, db_session
    ):
        import json
        from app.models.contact import JobContact
        from app.models.email_account import EmailAccount
        from app.models.job import Job
        from app.models.message import Message
        from app.models.message_extraction import MessageExtraction
        from app.services.job_processing import _create_contacts_for_job

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])

        account = EmailAccount(
            tenant_id=tenant_id,
            email_address="me@test.com",
            provider="gmail",
            oauth_encrypted="dummy",
        )
        db_session.add(account)
        db_session.flush()

        job = Job(
            tenant_id=tenant_id,
            company="Acme",
            role="SWE",
            current_stage="SOURCED",
        )
        db_session.add(job)
        db_session.flush()

        msg = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="msg-dup",
            raw_payload_json="{}",
            from_address="Recruiter <recruiter@acme.com>",
        )
        db_session.add(msg)
        db_session.flush()

        # Same contact twice with different roles (triggers UniqueViolation without fix)
        extraction = MessageExtraction(
            tenant_id=tenant_id,
            message_id=msg.id,
            status="completed",
            category="RECRUITER",
            event_type="FOLLOW_UP",
            company="Acme",
            role="SWE",
            contacts_json=json.dumps([
                {"email": "recruiter@acme.com", "name": "Jane", "role": "Recruiter"},
                {"email": "recruiter@acme.com", "name": "Jane", "role": "Engineering Manager"},
            ]),
            confidence=0.9,
            rationale="Test",
        )
        db_session.add(extraction)
        db_session.flush()

        _create_contacts_for_job(db_session, tenant_id, job, msg, extraction)
        db_session.commit()

        count = db_session.query(JobContact).filter(
            JobContact.tenant_id == tenant_id,
            JobContact.job_id == job.id,
        ).count()
        assert count == 1, "Same contact with two roles must produce exactly one JobContact"
