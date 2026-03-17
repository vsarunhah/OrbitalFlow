"""Tests for Phase 6: Jobs + reducer + timeline.

Covers:
  - Deterministic stage reducer rules
  - Manual override endpoint + audit logging
  - Job list / detail / timeline endpoints
"""

from __future__ import annotations

import uuid

import pytest

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
