"""Re-fetch a stored message from Gmail and refresh attachment metadata."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.providers.base import FetchedAttachment, FetchedMessage
from app.providers.gmail import GmailProvider, _extract_attachments

logger = logging.getLogger(__name__)


def parse_attachments_from_raw_payload(message: Message) -> list[FetchedAttachment]:
    """Parse attachment metadata from stored Gmail format=full JSON (no API call)."""
    try:
        raw = json.loads(message.raw_payload_json)
    except (json.JSONDecodeError, TypeError):
        return []
    payload = raw.get("payload") or {}
    if not payload:
        return []
    return _extract_attachments(payload)


def apply_attachment_metadata(
    db: Session,
    message: Message,
    attachments: list[FetchedAttachment],
) -> int:
    """Replace attachment rows for a message."""
    db.query(MessageAttachment).filter(
        MessageAttachment.message_id == message.id
    ).delete(synchronize_session=False)

    for att in attachments:
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
    return len(attachments)


def apply_fetched_attachments(
    db: Session,
    message: Message,
    fetched: FetchedMessage,
) -> int:
    """Replace attachment rows for a message from a fresh Gmail fetch."""
    return apply_attachment_metadata(db, message, fetched.attachments)


def ensure_message_attachments(
    db: Session,
    message: Message,
    account: EmailAccount | None = None,
    *,
    allow_gmail_fetch: bool = True,
) -> int:
    """Ensure attachment metadata exists: local payload parse, then optional Gmail fetch."""
    if message.attachments:
        return len(message.attachments)

    parsed = parse_attachments_from_raw_payload(message)
    if parsed:
        count = apply_attachment_metadata(db, message, parsed)
        db.flush()
        logger.info(
            "Backfilled %d attachment(s) from stored payload message_id=%s",
            count,
            message.id,
        )
        return count

    if not allow_gmail_fetch:
        return 0

    if account is None:
        account = (
            db.query(EmailAccount)
            .filter(EmailAccount.id == message.account_id)
            .first()
        )
    if account is None:
        return 0

    try:
        return refresh_message_from_gmail(db, message, account=account)
    except Exception:
        logger.warning(
            "Gmail attachment fetch failed message_id=%s",
            message.id,
            exc_info=True,
        )
        return 0


def ensure_attachments_for_messages(
    db: Session,
    messages: list[Message],
    *,
    allow_gmail_fetch: bool = True,
    gmail_fetch_limit: int = 3,
) -> set[uuid.UUID]:
    """Backfill missing attachment metadata for a batch of messages."""
    if not messages:
        return set()

    accounts_by_id: dict[uuid.UUID, EmailAccount] = {}
    if allow_gmail_fetch:
        account_ids = {m.account_id for m in messages if not m.attachments}
        if account_ids:
            rows = (
                db.query(EmailAccount)
                .filter(EmailAccount.id.in_(account_ids))
                .all()
            )
            accounts_by_id = {a.id: a for a in rows}

    updated_ids: set[uuid.UUID] = set()
    gmail_fetches = 0
    for message in messages:
        if message.attachments:
            continue

        parsed = parse_attachments_from_raw_payload(message)
        if parsed:
            apply_attachment_metadata(db, message, parsed)
            updated_ids.add(message.id)
            continue

        if allow_gmail_fetch and gmail_fetches < gmail_fetch_limit:
            account = accounts_by_id.get(message.account_id)
            if account is None:
                continue
            try:
                count = refresh_message_from_gmail(db, message, account=account)
                gmail_fetches += 1
                if count > 0:
                    updated_ids.add(message.id)
            except Exception:
                logger.warning(
                    "Gmail attachment fetch failed message_id=%s",
                    message.id,
                    exc_info=True,
                )

    if updated_ids:
        db.flush()
    return updated_ids


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
