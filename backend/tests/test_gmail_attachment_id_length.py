"""Gmail attachment ids can exceed 255 characters."""

import uuid

import pytest

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.models.tenant import Tenant
from app.providers.base import FetchedAttachment, FetchedMessage
from app.services.message_refresh import apply_fetched_attachments
from tests.conftest import TestSession


@pytest.fixture()
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def test_long_provider_attachment_id_persisted(db_session):
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
        raw_payload_json="{}",
        extraction_status="pending",
    )
    db_session.add(msg)
    db_session.flush()

    long_id = "ANGjdJ_" + ("x" * 300)
    fetched = FetchedMessage(
        provider_msg_id="g1",
        thread_id=None,
        subject=None,
        from_address=None,
        to_addresses=None,
        date_header=None,
        body_text=None,
        body_html=None,
        headers_json="{}",
        raw_payload_json="{}",
        label_ids_json=None,
        attachments=[
            FetchedAttachment(
                filename="offer.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                provider_attachment_id=long_id,
            )
        ],
    )
    apply_fetched_attachments(db_session, msg, fetched)
    db_session.commit()

    row = (
        db_session.query(MessageAttachment)
        .filter(MessageAttachment.message_id == msg.id)
        .one()
    )
    assert row.provider_attachment_id == long_id
    assert len(row.provider_attachment_id) > 255
