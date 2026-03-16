"""Tests for analytics API: summary, funnel, timeseries metrics."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.job import Job, JobEvent


def _create_job(db, tenant_id: uuid.UUID, *, stage="SOURCED", company="Acme", role="SWE"):
    job = Job(
        tenant_id=tenant_id,
        company=company,
        role=role,
        current_stage=stage,
    )
    db.add(job)
    db.flush()
    return job.id


def _create_event(db, tenant_id: uuid.UUID, job_id: uuid.UUID, event_type: str, created_at=None):
    ev = JobEvent(
        tenant_id=tenant_id,
        job_id=job_id,
        event_type=event_type,
        source="extraction",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(ev)
    db.flush()
    return ev.id


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def tenant_id_from_auth(client, auth_header):
    r = client.get("/auth/me", headers=auth_header)
    return uuid.UUID(r.json()["tenant_id"])


class TestAnalyticsSummary:
    def test_summary_empty(self, client, auth_header):
        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["total_jobs"] == 0
        assert data["by_stage"] == {}
        assert data["applications_received"] == 0
        assert data["interviews_detected"] == 0
        assert data["offers"] == 0
        assert data["rejections"] == 0
        assert data["conversion_application_to_interview"] == 0.0
        assert data["conversion_interview_to_offer"] == 0.0
        assert data["avg_days_applied_to_first_interview"] is None
        assert data["recent_activity_7d"] == 0
        assert data["recent_activity_30d"] == 0

    def test_summary_total_jobs_and_by_stage(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        _create_job(db_session, tid, stage="SOURCED", company="A", role="R1")
        _create_job(db_session, tid, stage="APPLIED", company="B", role="R2")
        _create_job(db_session, tid, stage="APPLIED", company="C", role="R3")
        _create_job(db_session, tid, stage="REJECTED", company="D", role="R4")
        db_session.commit()

        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["total_jobs"] == 4
        assert data["by_stage"]["SOURCED"] == 1
        assert data["by_stage"]["APPLIED"] == 2
        assert data["by_stage"]["REJECTED"] == 1
        assert data["rejections"] == 1

    def test_summary_applications_interviews_offers(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        j1 = _create_job(db_session, tid, stage="APPLIED", company="A", role="R1")
        j2 = _create_job(db_session, tid, stage="INTERVIEW", company="B", role="R2")
        j3 = _create_job(db_session, tid, stage="OFFER", company="C", role="R3")
        db_session.flush()

        _create_event(db_session, tid, j1, "APPLICATION_RECEIVED")
        _create_event(db_session, tid, j2, "APPLICATION_RECEIVED")
        _create_event(db_session, tid, j2, "INTERVIEW_SCHEDULED")
        _create_event(db_session, tid, j3, "APPLICATION_RECEIVED")
        _create_event(db_session, tid, j3, "INTERVIEW_REQUEST")
        _create_event(db_session, tid, j3, "OFFER")
        db_session.commit()

        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["applications_received"] == 3  # j1, j2, j3
        assert data["interviews_detected"] == 2   # j2, j3
        assert data["offers"] == 1                # j3 (has OFFER event and stage OFFER)
        assert data["conversion_application_to_interview"] == pytest.approx(2 / 3, abs=0.001)
        assert data["conversion_interview_to_offer"] == pytest.approx(0.5, abs=0.001)

    def test_summary_avg_days_applied_to_first_interview(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        base = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        j1 = _create_job(db_session, tid, stage="INTERVIEW", company="A", role="R1")
        db_session.flush()
        _create_event(db_session, tid, j1, "APPLICATION_RECEIVED", created_at=base)
        _create_event(db_session, tid, j1, "INTERVIEW_SCHEDULED", created_at=base + timedelta(days=5))
        db_session.commit()

        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["avg_days_applied_to_first_interview"] is not None
        assert data["avg_days_applied_to_first_interview"] == pytest.approx(5.0, abs=0.01)

    def test_summary_recent_activity(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        j1 = _create_job(db_session, tid, stage="APPLIED", company="A", role="R1")
        db_session.flush()
        now = datetime.now(timezone.utc)
        _create_event(db_session, tid, j1, "APPLICATION_RECEIVED", created_at=now - timedelta(days=2))
        _create_event(db_session, tid, j1, "FOLLOW_UP", created_at=now - timedelta(days=1))
        _create_event(db_session, tid, j1, "INTERVIEW_REQUEST", created_at=now - timedelta(days=10))
        db_session.commit()

        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["recent_activity_7d"] == 2
        assert data["recent_activity_30d"] == 3

    def test_summary_requires_auth(self, client):
        r = client.get("/analytics/summary")
        assert r.status_code == 401  # no bearer token

    def test_summary_tenant_isolation(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        _create_job(db_session, tid, company="Mine", role="R1")
        # Create second tenant via register and add a job for them
        r2 = client.post("/auth/register", json={
            "tenant_name": "OtherCo",
            "email": "other@test.com",
            "password": "otherpass",
        })
        assert r2.status_code in (200, 201)
        other_token = r2.json()["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {other_token}"})
        other_tenant_id = uuid.UUID(me.json()["tenant_id"])
        _create_job(db_session, other_tenant_id, company="Other", role="R2")
        db_session.commit()

        r = client.get("/analytics/summary", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["total_jobs"] == 1


class TestAnalyticsFunnel:
    def test_funnel_empty(self, client, auth_header):
        r = client.get("/analytics/funnel", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["milestones"]["applied"] == 0
        assert data["milestones"]["interview"] == 0
        assert data["milestones"]["offer"] == 0
        assert data["milestones"]["rejected"] == 0
        assert data["by_stage"] == {}

    def test_funnel_milestones(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        j1 = _create_job(db_session, tid, stage="APPLIED", company="A", role="R1")
        j2 = _create_job(db_session, tid, stage="INTERVIEW", company="B", role="R2")
        j3 = _create_job(db_session, tid, stage="REJECTED", company="C", role="R3")
        db_session.flush()
        _create_event(db_session, tid, j1, "APPLICATION_RECEIVED")
        _create_event(db_session, tid, j2, "APPLICATION_RECEIVED")
        _create_event(db_session, tid, j2, "INTERVIEW_SCHEDULED")
        db_session.commit()

        r = client.get("/analytics/funnel", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["milestones"]["applied"] == 2
        assert data["milestones"]["interview"] == 1
        assert data["milestones"]["rejected"] == 1
        assert data["by_stage"]["APPLIED"] == 1
        assert data["by_stage"]["INTERVIEW"] == 1
        assert data["by_stage"]["REJECTED"] == 1


class TestAnalyticsFunnelFlow:
    def test_funnel_flow_empty(self, client, auth_header):
        r = client.get("/analytics/funnel-flow", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["flows"] == []

    def test_funnel_flow_from_stage_history(self, client, auth_header, db_session, tenant_id_from_auth):
        from app.models.job import JobStageHistory

        tid = tenant_id_from_auth
        j1 = _create_job(db_session, tid, stage="INTERVIEW", company="A", role="R1")
        j2 = _create_job(db_session, tid, stage="APPLIED", company="B", role="R2")
        db_session.flush()
        db_session.add(
            JobStageHistory(
                tenant_id=tid,
                job_id=j1,
                stage_before="SOURCED",
                stage_after="APPLIED",
                source="auto",
            )
        )
        db_session.add(
            JobStageHistory(
                tenant_id=tid,
                job_id=j1,
                stage_before="APPLIED",
                stage_after="INTERVIEW",
                source="auto",
            )
        )
        db_session.commit()

        r = client.get("/analytics/funnel-flow", headers=auth_header)
        assert r.status_code == 200
        flows = r.json()["flows"]
        from_to = {(f["from_stage"], f["to_stage"]): f["value"] for f in flows}
        assert from_to.get(("SOURCED", "APPLIED")) == 1
        assert from_to.get(("APPLIED", "INTERVIEW")) == 1
        assert ("Entry", "APPLIED") not in from_to  # no Entry node; only actual transitions

    def test_funnel_flow_requires_auth(self, client):
        r = client.get("/analytics/funnel-flow")
        assert r.status_code == 401


class TestAnalyticsTimeseries:
    def test_timeseries_default_window(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        _create_job(db_session, tid, company="A", role="R1")
        db_session.commit()

        r = client.get("/analytics/timeseries", headers=auth_header)
        assert r.status_code == 200
        data = r.json()
        assert data["window"] == "30d"
        assert "jobs_created" in data
        assert "activity" in data

    def test_timeseries_window_param(self, client, auth_header):
        r = client.get("/analytics/timeseries?window=7d", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["window"] == "7d"
        r = client.get("/analytics/timeseries?window=90d", headers=auth_header)
        assert r.status_code == 200
        assert r.json()["window"] == "90d"

    def test_timeseries_jobs_created_bucketed(self, client, auth_header, db_session, tenant_id_from_auth):
        tid = tenant_id_from_auth
        base = datetime.now(timezone.utc) - timedelta(days=5)
        j1 = _create_job(db_session, tid, company="A", role="R1")
        db_session.query(Job).filter(Job.id == j1).update({"created_at": base})
        j2 = _create_job(db_session, tid, company="B", role="R2")
        db_session.query(Job).filter(Job.id == j2).update({"created_at": base})
        db_session.commit()

        r = client.get("/analytics/timeseries?window=30d", headers=auth_header)
        assert r.status_code == 200
        jobs_created = {p["date"]: p["count"] for p in r.json()["jobs_created"]}
        date_str = base.date().isoformat()
        assert date_str in jobs_created
        assert jobs_created[date_str] == 2

    def test_timeseries_requires_auth(self, client):
        r = client.get("/analytics/timeseries?window=7d")
        assert r.status_code == 401
