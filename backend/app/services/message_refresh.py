"""Re-fetch a stored message from Gmail and refresh attachment metadata."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.providers.base import FetchedMessage
from app.providers.gmail import GmailProvider

logger = logging.getLogger(__name__)


def apply_fetched_attachments(
    db: Session,
    message: Message,
    fetched: FetchedMessage,
) -> int:
    """Replace attachment rows for a message from a fresh Gmail fetch."""
    db.query(MessageAttachment).filter(
        MessageAttachment.message_id == message.id
    ).delete(synchronize_session=False)

    count = 0
    for att in fetched.attachments:
        db.add(
            MessageAttachment(
                tenant_id=message.tenant_id,
                message_id=message.id,
                filename=att.filename[:512],
                mime_type=att.mime_type,
                size_bytes=att.size_bytes,
                provider_attachment_id=att.provider_attachment_id,
            )
        )
        count += 1
    return count


def refresh_message_from_gmail(
    db: Session,
    message: Message,
    *,
    account: EmailAccount | None = None,
) -> int:
    """Re-fetch message from Gmail; update body fields and attachment metadata.

    Returns the number of attachments stored after refresh.
    """
    if account is None:
        account = (
            db.query(EmailAccount)
            .filter(EmailAccount.id == message.account_id)
            .first()
        )
    if account is None:
        raise ValueError("Email account not found for message")

    provider = GmailProvider(db_session=db)
    fetched = provider.fetch_message(account, message.provider_msg_id)

    message.thread_id = fetched.thread_id
    message.subject = fetched.subject
    message.from_address = fetched.from_address
    message.to_addresses = fetched.to_addresses
    message.body_text = fetched.body_text
    message.body_html = fetched.body_html
    message.headers_json = fetched.headers_json
    message.raw_payload_json = fetched.raw_payload_json
    message.label_ids_json = fetched.label_ids_json

    if fetched.date_header:
        try:
            message.date_header = datetime.fromisoformat(fetched.date_header)
        except (ValueError, TypeError):
            pass

    count = apply_fetched_attachments(db, message, fetched)
    db.flush()
    logger.info(
        "Refreshed message id=%s provider_msg_id=%s attachments=%d",
        message.id,
        message.provider_msg_id,
        count,
    )
    return count


def refresh_message_by_id(
    db: Session,
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
) -> tuple[Message, int]:
    message = (
        db.query(Message)
        .filter(Message.id == message_id, Message.tenant_id == tenant_id)
        .first()
    )
    if message is None:
        raise LookupError("Message not found")
    count = refresh_message_from_gmail(db, message)
    db.commit()
    db.refresh(message)
    return message, count
