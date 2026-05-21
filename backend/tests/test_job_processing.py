"""Tests for job resolution / fuzzy matching (Paraform platform edge cases)."""

from __future__ import annotations

import uuid

import pytest

from app.models.email_account import EmailAccount
from app.models.job import Job, JobIdentity
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.models.tenant import Tenant
from app.services.job_processing import (
    _fuzzy_match,
    _identity_belongs_to_job,
    _should_store_identity,
    process_extraction_for_job,
)


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession

    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _seed_tenant(db, tenant_id: uuid.UUID | None = None) -> uuid.UUID:
    tenant_id = tenant_id or uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="TestCo"))
    db.flush()
    return tenant_id


def _seed_message(db, tenant_id: uuid.UUID) -> tuple[EmailAccount, Message]:
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        provider="gmail",
        oauth_encrypted="dummy",
    )
    db.add(account)
    db.flush()

    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id=f"msg-{uuid.uuid4()}",
        raw_payload_json="{}",
        from_address="Recruiter <rec@example.com>",
        thread_id=f"thread-{uuid.uuid4()}",
    )
    db.add(msg)
    db.flush()
    return account, msg


class TestParaformPlatformMatching:
    def test_stale_paraform_identity_does_not_match_afterquery_job(self, db_session):
        tenant_id = _seed_tenant(db_session)
        job = Job(
            tenant_id=tenant_id,
            company="AfterQuery",
            role="Software Engineer",
            current_stage="INTERVIEW",
        )
        db_session.add(job)
        db_session.flush()

        # Simulates job created as Paraform then renamed, or platform mis-extraction.
        db_session.add(
            JobIdentity(
                tenant_id=tenant_id,
                job_id=job.id,
                company="Paraform",
                role="Software Engineer",
            )
        )
        db_session.commit()

        identity = db_session.query(JobIdentity).first()
        assert identity is not None
        assert not _identity_belongs_to_job(job, identity)
        matched = _fuzzy_match(db_session, tenant_id, "Paraform", "product engineer")
        assert matched is None

    def test_paraform_recruiter_outreach_creates_new_job_not_afterquery(self, db_session):
        tenant_id = _seed_tenant(db_session)
        afterquery = Job(
            tenant_id=tenant_id,
            company="AfterQuery",
            role="Software Engineer",
            current_stage="INTERVIEW",
        )
        db_session.add(afterquery)
        db_session.flush()
        db_session.add(
            JobIdentity(
                tenant_id=tenant_id,
                job_id=afterquery.id,
                company="Paraform",
                role="Software Engineer",
            )
        )
        db_session.flush()

        _, msg = _seed_message(db_session, tenant_id)
        extraction = MessageExtraction(
            tenant_id=tenant_id,
            message_id=msg.id,
            status="completed",
            category="RECRUITER",
            event_type="NONE",
            company="Paraform",
            role="product engineer",
            confidence=0.9,
            rationale="Cold outreach for Paraform engineering role.",
        )
        db_session.add(extraction)
        db_session.flush()

        result = process_extraction_for_job(db_session, msg, extraction)
        assert result is not None
        assert result.company == "Paraform"
        assert result.id != afterquery.id

    def test_paraform_identity_on_paraform_job_still_matches(self, db_session):
        tenant_id = _seed_tenant(db_session)
        job = Job(
            tenant_id=tenant_id,
            company="Paraform",
            role="Software Engineer",
            current_stage="SOURCED",
        )
        db_session.add(job)
        db_session.flush()
        identity = JobIdentity(
            tenant_id=tenant_id,
            job_id=job.id,
            company="Paraform",
            role="Software Engineer",
        )
        db_session.add(identity)
        db_session.commit()

        assert _identity_belongs_to_job(job, identity)
        matched = _fuzzy_match(db_session, tenant_id, "Paraform", "product engineer")
        assert matched is not None
        assert matched.id == job.id

    def test_should_not_store_paraform_alias_on_employer_job(self):
        job = Job(company="AfterQuery", role="Software Engineer", current_stage="SOURCED")
        assert not _should_store_identity(job, "Paraform")

    def test_should_store_identity_for_same_employer(self):
        job = Job(company="AfterQuery", role="Software Engineer", current_stage="SOURCED")
        assert _should_store_identity(job, "AfterQuery")
