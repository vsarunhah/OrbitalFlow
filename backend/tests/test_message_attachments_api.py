"""API tests for message attachment timeline and download routing."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from tests.conftest import TestSession


@pytest.fixture()
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _seed_message_with_attachment(db, tenant_id, account_id):
    msg = Message(
        tenant_id=tenant_id,
        account_id=account_id,
        provider_msg_id="gmail-msg-1",
        thread_id="thread-1",
        subject="With PDF",
        body_text="See attached",
        raw_payload_json="{}",
        extraction_status="pending",
    )
    db.add(msg)
    db.flush()
    att = MessageAttachment(
        tenant_id=tenant_id,
        message_id=msg.id,
        filename="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        provider_attachment_id="att-gmail-1",
    )
    db.add(att)
    db.commit()
    db.refresh(msg)
    db.refresh(att)
    return msg, att


@pytest.fixture()
def account_and_message(client, auth_header, db_session):
    from app.encryption import encrypt

    tenant_id = uuid.UUID(client.get("/auth/me", headers=auth_header).json()["tenant_id"])
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        oauth_encrypted=encrypt('{"access_token":"x","refresh_token":"y"}'),
        status="active",
    )
    db_session.add(account)
    db_session.commit()
    msg, att = _seed_message_with_attachment(db_session, tenant_id, account.id)
    return tenant_id, msg, att, account


def test_timeline_includes_per_message_attachments(client, auth_header, account_and_message, db_session):
    from app.models.job import Job, JobThread

    tenant_id, msg, att, _account = account_and_message
    db = db_session
    job = Job(tenant_id=tenant_id, company="Acme", role="Engineer", current_stage="APPLIED")
    db.add(job)
    db.flush()
    db.add(JobThread(tenant_id=tenant_id, job_id=job.id, thread_id=msg.thread_id))
    db.commit()

    r = client.get(f"/jobs/{job.id}/timeline", headers=auth_header)
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) == 1
    assert len(messages[0]["attachments"]) == 1
    assert messages[0]["attachments"][0]["filename"] == "doc.pdf"
    assert messages[0]["attachments"][0]["id"] == str(att.id)


@patch("app.routers.messages.GmailProvider")
def test_download_attachment_proxies_gmail(mock_provider_cls, client, auth_header, account_and_message):
    _tenant_id, msg, att, _account = account_and_message
    mock_provider = MagicMock()
    mock_provider.fetch_attachment.return_value = b"%PDF-1.4 fake"
    mock_provider_cls.return_value = mock_provider

    r = client.get(
        f"/messages/{msg.id}/attachments/{att.id}",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 fake"
    assert "doc.pdf" in r.headers.get("content-disposition", "")
    mock_provider.fetch_attachment.assert_called_once()
