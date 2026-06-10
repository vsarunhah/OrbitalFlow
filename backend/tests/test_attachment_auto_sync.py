"""Automatic attachment metadata backfill from stored Gmail payload."""

import json
import uuid

import pytest

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.models.tenant import Tenant
from app.services.message_refresh import (
    ensure_attachments_for_messages,
    parse_attachments_from_raw_payload,
)
from tests.conftest import TestSession


@pytest.fixture()
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _payload_with_pdf() -> dict:
    return {
        "id": "gmail-1",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "SGVsbG8="}},
                {
                    "mimeType": "application/pdf",
                    "filename": "Varun Offer.pdf",
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": 'attachment; filename="Varun Offer.pdf"',
                        }
                    ],
                    "body": {"attachmentId": "abc123", "size": 1000},
                },
            ],
        },
    }


def test_parse_attachments_from_stored_payload(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(id=tenant_id, name="T"))
    db_session.flush()
    msg = Message(
        tenant_id=tenant_id,
        account_id=uuid.uuid4(),
        provider_msg_id="g1",
        raw_payload_json=json.dumps(_payload_with_pdf()),
        extraction_status="pending",
    )
    parsed = parse_attachments_from_raw_payload(msg)
    assert len(parsed) == 1
    assert parsed[0].filename == "Varun Offer.pdf"


def test_ensure_attachments_backfills_on_timeline(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(id=tenant_id, name="T"))
    db_session.flush()
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        oauth_encrypted=encrypt('{"access_token":"x"}'),
        status="active",
    )
    db_session.add(account)
    db_session.flush()
    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="g1",
        raw_payload_json=json.dumps(_payload_with_pdf()),
        extraction_status="completed",
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    updated = ensure_attachments_for_messages(
        db_session, [msg], allow_gmail_fetch=False
    )
    db_session.commit()
    db_session.refresh(msg, ["attachments"])

    assert msg.id in updated
    assert len(msg.attachments) == 1
    assert msg.attachments[0].filename == "Varun Offer.pdf"
