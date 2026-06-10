"""Extract text from inbound PDF attachments for LLM extraction."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.providers.gmail import (
    GmailProvider,
    fetch_inline_attachment_bytes,
)
from app.services.resume_parser import extract_text_from_pdf

logger = logging.getLogger(__name__)

MAX_PDF_ATTACHMENTS = 3
MAX_EXTRACTED_TEXT_STORE = 8000
MAX_PROMPT_CHARS_PER_FILE = 4000


def collect_attachment_texts_for_extraction(
    db: Session, message: Message
) -> list[tuple[str, str]]:
    """Return (filename, excerpt) for PDF attachments; cache text on rows."""
    attachments = (
        db.query(MessageAttachment)
        .filter(MessageAttachment.message_id == message.id)
        .order_by(MessageAttachment.created_at.asc())
        .all()
    )
    pdf_rows = [
        a
        for a in attachments
        if (a.mime_type or "").lower() == "application/pdf"
    ][:MAX_PDF_ATTACHMENTS]

    if not pdf_rows:
        return []

    account = (
        db.query(EmailAccount)
        .filter(EmailAccount.id == message.account_id)
        .first()
    )
    if account is None:
        return []

    provider = GmailProvider(db_session=db)
    results: list[tuple[str, str]] = []

    for row in pdf_rows:
        if row.extracted_text:
            excerpt = row.extracted_text[:MAX_PROMPT_CHARS_PER_FILE]
            results.append((row.filename, excerpt))
            continue

        try:
            raw = _fetch_attachment_bytes(
                provider, account, message, row
            )
            if raw is None:
                continue
            text = extract_text_from_pdf(raw)
            stored = text[:MAX_EXTRACTED_TEXT_STORE]
            row.extracted_text = stored
            db.flush()
            results.append((row.filename, stored[:MAX_PROMPT_CHARS_PER_FILE]))
        except Exception:
            logger.warning(
                "Failed to extract PDF attachment message_id=%s filename=%s",
                message.id,
                row.filename,
                exc_info=True,
            )

    return results


def _fetch_attachment_bytes(
    provider: GmailProvider,
    account: EmailAccount,
    message: Message,
    row: MessageAttachment,
) -> bytes | None:
    if row.provider_attachment_id:
        return provider.fetch_attachment(
            account,
            message.provider_msg_id,
            row.provider_attachment_id,
        )
    try:
        raw = json.loads(message.raw_payload_json)
        payload = raw.get("payload", {})
        return fetch_inline_attachment_bytes(payload, row.filename)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
