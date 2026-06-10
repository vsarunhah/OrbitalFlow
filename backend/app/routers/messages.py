"""Message attachment download API."""

from __future__ import annotations

import json
import logging
import uuid
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_attachment import MessageAttachment
from app.providers.gmail import (
    GmailProvider,
    MAX_ATTACHMENT_SIZE_BYTES,
    TokenRefreshError,
    fetch_inline_attachment_bytes,
)
from app.services.message_refresh import refresh_message_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/{message_id}/refresh")
def refresh_message(
    message_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-fetch this email from Gmail (metadata + attachments). Use after upgrading ingest."""
    try:
        message, attachment_count = refresh_message_by_id(
            db, auth.tenant_id, message_id
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        ) from None
    except TokenRefreshError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reconnect Gmail in Settings to refresh this email.",
        ) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reconnect Gmail in Settings to refresh this email.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not refresh message from Gmail.",
        ) from exc
    except Exception as exc:
        logger.exception("refresh_message failed message_id=%s", message_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not refresh message from Gmail.",
        ) from exc

    return {
        "message_id": str(message.id),
        "attachments_count": attachment_count,
    }


@router.get("/{message_id}/attachments/{attachment_id}")
def download_message_attachment(
    message_id: uuid.UUID,
    attachment_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream an inbound attachment from Gmail (tenant-scoped, per message)."""
    row = (
        db.query(MessageAttachment)
        .filter(
            MessageAttachment.id == attachment_id,
            MessageAttachment.message_id == message_id,
            MessageAttachment.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    message = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            Message.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.id == message.account_id,
            EmailAccount.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email account not found for this message.",
        )

    if row.size_bytes is not None and row.size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment exceeds maximum size (25MB).",
        )

    try:
        data = _fetch_bytes(account, message, row, db)
    except TokenRefreshError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reconnect Gmail in Settings to download attachments.",
        ) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reconnect Gmail in Settings to download attachments.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch attachment from Gmail.",
        ) from exc

    if len(data) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment exceeds maximum size (25MB).",
        )

    media_type = row.mime_type or "application/octet-stream"
    filename = row.filename or "attachment"
    # RFC 5987 for names with spaces/special chars; quoted fallback for older clients
    encoded = quote(filename)
    disposition = (
        f"attachment; filename=\"{filename.replace(chr(34), '')}\"; "
        f"filename*=UTF-8''{encoded}"
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


def _fetch_bytes(
    account: EmailAccount,
    message: Message,
    row: MessageAttachment,
    db: Session,
) -> bytes:
    provider = GmailProvider(db_session=db)
    if row.provider_attachment_id:
        return provider.fetch_attachment(
            account,
            message.provider_msg_id,
            row.provider_attachment_id,
        )
    raw = json.loads(message.raw_payload_json)
    inline = fetch_inline_attachment_bytes(raw.get("payload", {}), row.filename)
    if inline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment content not available.",
        )
    return inline
