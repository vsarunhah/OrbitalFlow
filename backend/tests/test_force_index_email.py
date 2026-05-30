"""Tests for force-indexing a Gmail link into a job."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message
from app.providers.base import FetchedMessage
from app.services.force_index_email import ForceIndexError, force_index_email_link


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession

    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _seed_account(db, tenant_id: uuid.UUID, email: str = "test@test.com") -> EmailAccount:
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address=email,
        provider="gmail",
        oauth_encrypted=encrypt(json.dumps({"access_token": "fake"})),
    )
    db.add(account)
    db.flush()
    return account


def _fetched(provider_msg_id: str, thread_id: str) -> FetchedMessage:
    return FetchedMessage(
        provider_msg_id=provider_msg_id,
        thread_id=thread_id,
        subject="Test",
        from_address="Recruiter <rec@acme.com>",
        to_addresses="me@test.com",
        date_header=None,
        body_text="Hello",
        body_html=None,
        headers_json="{}",
        raw_payload_json="{}",
        label_ids_json=None,
    )


class TestForceIndexEmailLink:
    def test_links_existing_message_to_existing_job(self, client, auth_header, db_session):
        job_id, tenant_id = _create_job(client, auth_header, db_session)
        account = _seed_account(db_session, tenant_id)
        msg = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="force-msg-1",
            thread_id="force-thread-1",
            subject="Interview follow-up",
            raw_payload_json="{}",
            from_address="Recruiter <rec@acme.com>",
            date_header=datetime.now(timezone.utc),
        )
        db_session.add(msg)
        db_session.commit()

        with patch(
            "app.services.force_index_email.list_thread_message_ids",
            return_value=["force-msg-1"],
        ), patch(
            "app.providers.gmail.GmailProvider.fetch_message",
            return_value=_fetched("force-msg-1", "force-thread-1"),
        ):
            result = force_index_email_link(
                db_session,
                tenant_id,
                "https://mail.google.com/mail/u/0/#all/force-msg-1",
                job_id=job_id,
            )

        assert result.job_id == job_id
        assert result.job_created is False
        assert result.messages_ingested == 0
        assert result.messages_linked >= 1

        thread = (
            db_session.query(JobThread)
            .filter(JobThread.thread_id == "force-thread-1")
            .first()
        )
        assert thread is not None
        assert thread.job_id == job_id

        event = (
            db_session.query(JobEvent)
            .filter(JobEvent.job_id == job_id, JobEvent.message_id == msg.id)
            .first()
        )
        assert event is not None
        assert event.source == "manual_import"

    def test_creates_new_job_when_no_job_id(self, client, auth_header, db_session):
        _, tenant_id = _create_job(client, auth_header, db_session)
        account = _seed_account(db_session, tenant_id)
        db_session.add(
            Message(
                tenant_id=tenant_id,
                account_id=account.id,
                provider_msg_id="force-msg-2",
                thread_id="force-thread-2",
                subject="Offer letter",
                raw_payload_json="{}",
                from_address="HR <hr@startup.com>",
                date_header=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        with patch(
            "app.services.force_index_email.list_thread_message_ids",
            return_value=["force-msg-2"],
        ), patch(
            "app.providers.gmail.GmailProvider.fetch_message",
            return_value=_fetched("force-msg-2", "force-thread-2"),
        ):
            result = force_index_email_link(
                db_session,
                tenant_id,
                "https://mail.google.com/mail/u/0/#all/force-msg-2",
                company="StartupCo",
                role="Backend Engineer",
            )

        assert result.job_created is True
        job = db_session.query(Job).filter(Job.id == result.job_id).first()
        assert job is not None
        assert job.company == "StartupCo"
        assert job.role == "Backend Engineer"

    def test_reassigns_thread_from_old_job(self, client, auth_header, db_session):
        job_a, tenant_id = _create_job(client, auth_header, db_session, company="OldCo")
        job_b, _ = _create_job(client, auth_header, db_session, company="NewCo")
        account = _seed_account(db_session, tenant_id)
        msg = Message(
            tenant_id=tenant_id,
            account_id=account.id,
            provider_msg_id="force-msg-3",
            thread_id="force-thread-3",
            subject="Moved thread",
            raw_payload_json="{}",
            from_address="Recruiter <rec@acme.com>",
            date_header=datetime.now(timezone.utc),
        )
        db_session.add(msg)
        db_session.flush()
        db_session.add(
            JobThread(tenant_id=tenant_id, job_id=job_a, thread_id="force-thread-3")
        )
        db_session.commit()

        with patch(
            "app.services.force_index_email.list_thread_message_ids",
            return_value=["force-msg-3"],
        ), patch(
            "app.providers.gmail.GmailProvider.fetch_message",
            return_value=_fetched("force-msg-3", "force-thread-3"),
        ):
            force_index_email_link(
                db_session,
                tenant_id,
                "https://mail.google.com/mail/u/0/#all/force-msg-3",
                job_id=job_b,
            )

        thread = (
            db_session.query(JobThread)
            .filter(JobThread.thread_id == "force-thread-3")
            .one()
        )
        assert thread.job_id == job_b

    def test_api_endpoint(self, client, auth_header, db_session):
        job_id, tenant_id = _create_job(client, auth_header, db_session)
        account = _seed_account(db_session, tenant_id)
        db_session.add(
            Message(
                tenant_id=tenant_id,
                account_id=account.id,
                provider_msg_id="force-msg-4",
                thread_id="force-thread-4",
                subject="API test",
                raw_payload_json="{}",
                from_address="Recruiter <rec@acme.com>",
                date_header=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        with patch(
            "app.services.force_index_email.list_thread_message_ids",
            return_value=["force-msg-4"],
        ), patch(
            "app.providers.gmail.GmailProvider.fetch_message",
            return_value=_fetched("force-msg-4", "force-thread-4"),
        ):
            r = client.post(
                "/jobs/import-email-link",
                headers=auth_header,
                json={
                    "email_url": "https://mail.google.com/mail/u/0/#all/force-msg-4",
                    "job_id": str(job_id),
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["job_id"] == str(job_id)
        assert data["job_created"] is False
        assert data["messages_linked"] >= 1

    def test_no_account_raises(self, client, auth_header, db_session):
        _, tenant_id = _create_job(client, auth_header, db_session)
        with pytest.raises(ForceIndexError, match="No connected Gmail"):
            force_index_email_link(
                db_session,
                tenant_id,
                "https://mail.google.com/mail/u/0/#all/abc123456789",
            )


def _create_job(client, auth_header, db_session, *, company="Acme", role="SWE"):
    from app.models.job import Job as JobModel

    tenant_id = uuid.UUID(client.get("/auth/me", headers=auth_header).json()["tenant_id"])
    job = JobModel(
        tenant_id=tenant_id,
        company=company,
        role=role,
        current_stage="SOURCED",
    )
    db_session.add(job)
    db_session.commit()
    return job.id, tenant_id
