"""Tests for re-fetching messages from Gmail (attachment backfill)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.tenant import Tenant
from app.models.message_attachment import MessageAttachment
from app.providers.base import FetchedAttachment, FetchedMessage
from app.services.message_refresh import refresh_message_from_gmail
from tests.conftest import TestSession


@pytest.fixture()
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def test_refresh_replaces_attachment_rows(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(id=tenant_id, name="T"))
    db_session.flush()
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        oauth_encrypted=encrypt('{"access_token":"x","refresh_token":"y"}'),
        status="active",
    )
    db_session.add(account)
    db_session.flush()

    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="gmail-1",
        thread_id="t1",
        subject="Offer",
        body_text="See attached",
        raw_payload_json="{}",
        extraction_status="completed",
    )
    db_session.add(msg)
    db_session.flush()
    db_session.add(
        MessageAttachment(
            tenant_id=tenant_id,
            message_id=msg.id,
            filename="old.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            provider_attachment_id="old-id",
        )
    )
    db_session.commit()

    fetched = FetchedMessage(
        provider_msg_id="gmail-1",
        thread_id="t1",
        subject="Offer",
        from_address="hr@co.com",
        to_addresses="me@test.com",
        date_header=None,
        body_text="See attached",
        body_html=None,
        headers_json="{}",
        raw_payload_json='{"id":"gmail-1"}',
        label_ids_json=None,
        attachments=[
            FetchedAttachment(
                filename="Offer_Letter.pdf",
                mime_type="application/pdf",
                size_bytes=5000,
                provider_attachment_id="new-id",
            )
        ],
    )

    with patch("app.services.message_refresh.GmailProvider") as mock_cls:
        mock_cls.return_value.fetch_message.return_value = fetched
        count = refresh_message_from_gmail(db_session, msg, account=account)
        db_session.commit()

    assert count == 1
    rows = (
        db_session.query(MessageAttachment)
        .filter(MessageAttachment.message_id == msg.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].filename == "Offer_Letter.pdf"
    assert rows[0].provider_attachment_id == "new-id"


@patch("app.routers.messages.refresh_message_by_id")
def test_refresh_api_endpoint(mock_refresh, client, auth_header):
    msg_id = uuid.uuid4()
    mock_refresh.return_value = (MagicMock(id=msg_id), 2)
    r = client.post(f"/messages/{msg_id}/refresh", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["attachments_count"] == 2
