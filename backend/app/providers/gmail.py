"""Gmail implementation of EmailProvider.

Uses httpx to call the Gmail REST API directly (no google-api-python-client
dependency). Handles OAuth token refresh transparently.
Supports sending messages (messages.send) and replying in thread.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime

import httpx

from app.encryption import decrypt, encrypt
from app.models.email_account import EmailAccount
from app.providers.base import (
    EmailProvider,
    FetchedAttachment,
    FetchedMessage,
    SendResult,
)

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_ATTACHMENT_SIZE_BYTES = 25_000_000


@dataclass(frozen=True)
class OutboundAttachment:
    """File to attach to an outbound message (RFC 2045 MIME)."""
    filename: str
    data: bytes
    content_type: str | None = None


class TokenRefreshError(Exception):
    """Raised when OAuth token refresh fails (e.g. revoked refresh token or invalid client credentials)."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GmailProvider(EmailProvider):
    """Fetch a single Gmail message using messages.get(format=full)."""

    def __init__(self, db_session=None):
        self._db = db_session

    def fetch_message(
        self, account: EmailAccount, message_id: str
    ) -> FetchedMessage:
        logger.info(
            "Fetching message provider_msg_id=%s for account_id=%s",
            message_id,
            account.id,
        )
        creds = _get_credentials(account)
        access_token = _ensure_valid_token(account, creds, self._db)

        url = f"{GMAIL_API_BASE}/messages/{message_id}"
        resp = httpx.get(
            url,
            params={"format": "full"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()

        return _parse_message(raw)

    def fetch_attachment(
        self,
        account: EmailAccount,
        message_id: str,
        provider_attachment_id: str,
    ) -> bytes:
        """Fetch attachment bytes via Gmail users.messages.attachments.get."""
        creds = _get_credentials(account)
        access_token = _ensure_valid_token(account, creds, self._db)
        url = (
            f"{GMAIL_API_BASE}/messages/{message_id}/attachments/"
            f"{provider_attachment_id}"
        )
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_data = data.get("data", "")
        return base64.urlsafe_b64decode(raw_data + "==")

    def send_message(
        self,
        account: EmailAccount,
        to_addrs: list[str],
        subject: str,
        body_text: str,
        *,
        cc_addrs: list[str] | None = None,
        thread_id: str | None = None,
        references: str | None = None,
        in_reply_to: str | None = None,
        attachments: list[OutboundAttachment] | None = None,
    ) -> SendResult:
        """Send an email via Gmail API. Optionally reply in thread with thread_id and headers."""
        if not to_addrs:
            raise ValueError("At least one To address is required")
        creds = _get_credentials(account)
        access_token = _ensure_valid_token(account, creds, self._db)

        msg = EmailMessage()
        if account.display_name and account.display_name.strip():
            msg["From"] = formataddr((account.display_name.strip(), account.email_address))
        else:
            msg["From"] = account.email_address
        msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)
        msg["Subject"] = subject or "(no subject)"
        if references:
            msg["References"] = references
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        msg.set_content(body_text or "", subtype="plain")
        for att in attachments or []:
            ctype = att.content_type or mimetypes.guess_type(att.filename)[0]
            if not ctype:
                ctype = "application/octet-stream"
            maintype, _, subtype = ctype.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(
                att.data,
                maintype=maintype,
                subtype=subtype,
                filename=att.filename,
            )

        raw_bytes = msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")

        body: dict = {"raw": raw_b64}
        if thread_id:
            body["threadId"] = thread_id

        url = f"{GMAIL_API_BASE}/messages/send"
        timeout = 120.0 if len(raw_bytes) > 2_000_000 else 30.0
        resp = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        return SendResult(
            provider_message_id=result["id"],
            thread_id=result.get("threadId") or thread_id,
        )


def _get_credentials(account: EmailAccount) -> dict:
    return json.loads(decrypt(account.oauth_encrypted))


def _ensure_valid_token(
    account: EmailAccount, creds: dict, db_session=None
) -> str:
    """Return a usable access token, refreshing if needed.

    We optimistically use the stored token. If a 401 comes back the caller
    should refresh; but for simplicity we pro-actively refresh when we know
    the token is likely expired (no expires_at stored yet → always refresh
    on first call).
    """
    access_token = creds.get("access_token", "")
    refresh_token = creds.get("refresh_token")

    if not refresh_token:
        logger.warning(
            "No refresh_token for account_id=%s; using existing access_token",
            account.id,
        )
        return access_token

    from app.config import settings

    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )

    if resp.status_code != 200:
        body = resp.text
        logger.error(
            "Token refresh failed for account_id=%s status=%s body=%s",
            account.id,
            resp.status_code,
            body,
        )
        raise TokenRefreshError(
            f"Gmail token refresh failed for account_id={account.id}. "
            "Reconnect the account in Settings (refresh token may be revoked or client credentials invalid).",
            status_code=resp.status_code,
            response_body=body,
        )

    new_tokens = resp.json()
    new_access = new_tokens["access_token"]
    creds["access_token"] = new_access

    if db_session is not None:
        account.oauth_encrypted = encrypt(json.dumps(creds))
        db_session.commit()
        logger.info("Refreshed and persisted token for account_id=%s", account.id)

    return new_access


def verify_gmail_connection(
    account: EmailAccount, db_session
) -> tuple[bool, str | None]:
    """Validate OAuth: refresh if possible, otherwise ensure Gmail API accepts the token.

    Returns (True, None) on success, (False, user-facing error message) on failure.
    """
    try:
        creds = _get_credentials(account)
        had_refresh = bool(creds.get("refresh_token"))
        access_token = _ensure_valid_token(account, creds, db_session)
        if not had_refresh:
            resp = httpx.get(
                f"{GMAIL_API_BASE}/profile",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if resp.status_code == 401:
                return False, (
                    "Gmail access expired. Reconnect your account in Settings."
                )
            resp.raise_for_status()
    except TokenRefreshError:
        return False, (
            "Gmail authentication failed. Reconnect your account in Settings "
            "(your Google session may have expired or access was revoked)."
        )
    except Exception:
        logger.exception(
            "verify_gmail_connection failed for account_id=%s", account.id
        )
        return False, "Could not verify Gmail connection. Try again or reconnect."
    return True, None


# System labels that mean the message should not drive job tracking.
_SKIP_INGEST_LABELS = frozenset({"DRAFT", "TRASH", "SPAM"})


def should_skip_ingest(label_ids: list[str] | None) -> bool:
    """True when Gmail labels indicate draft, spam, or trash."""
    if not label_ids:
        return False
    return bool(_SKIP_INGEST_LABELS.intersection(label_ids))


def _parse_message(raw: dict) -> FetchedMessage:
    """Parse a Gmail API messages.get(format=full) response."""
    payload = raw.get("payload", {})
    headers_list = payload.get("headers", [])

    headers_map = {}
    for h in headers_list:
        name_lower = h["name"].lower()
        headers_map[name_lower] = h["value"]

    subject = headers_map.get("subject")
    from_addr = headers_map.get("from")
    to_addrs = headers_map.get("to")
    date_str = headers_map.get("date")

    date_header_iso: str | None = None
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            date_header_iso = dt.isoformat()
        except Exception:
            logger.debug("Could not parse date header: %s", date_str)

    body_text, body_html = _extract_body(payload)
    attachments = _extract_attachments(payload)

    label_ids = raw.get("labelIds")

    return FetchedMessage(
        provider_msg_id=raw["id"],
        thread_id=raw.get("threadId"),
        subject=subject,
        from_address=from_addr,
        to_addresses=to_addrs,
        date_header=date_header_iso,
        body_text=body_text,
        body_html=body_html,
        headers_json=json.dumps(headers_map),
        raw_payload_json=json.dumps(raw),
        label_ids_json=json.dumps(label_ids) if label_ids else None,
        attachments=attachments,
    )


def _part_headers_map(part: dict) -> dict[str, str]:
    headers: dict[str, str] = {}
    for h in part.get("headers", []):
        headers[h["name"].lower()] = h["value"]
    return headers


def _decode_body_data(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "==")


def _extract_attachments(payload: dict) -> list[FetchedAttachment]:
    """Walk MIME tree and collect non-body attachment parts."""
    results: list[FetchedAttachment] = []
    seen: set[tuple[str | None, str]] = set()

    def _walk(part: dict, parent_mime: str = "") -> None:
        mime = part.get("mimeType", "")
        headers = _part_headers_map(part)
        disposition = headers.get("content-disposition", "")
        filename = (
            part.get("filename")
            or headers.get("content-filename")
            or _filename_from_disposition(disposition)
            or _filename_from_content_type(headers.get("content-type", ""))
        )
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        inline_data = body.get("data")
        size = body.get("size")

        if mime.startswith("multipart/"):
            for sub in part.get("parts", []):
                _walk(sub, mime)
            return

        if mime.startswith("message/") and part.get("parts"):
            for sub in part.get("parts", []):
                _walk(sub, mime)

        is_body_part = mime in ("text/plain", "text/html") and (
            parent_mime == "multipart/alternative"
            or (not filename and "attachment" not in disposition.lower())
        )
        if is_body_part:
            return

        has_attachment = bool(
            filename
            or "attachment" in disposition.lower()
            or (mime and not mime.startswith("multipart/") and mime not in ("text/plain", "text/html"))
        )
        if not has_attachment:
            return

        if not filename:
            ext = mimetypes.guess_extension(mime.split(";")[0].strip()) or ""
            filename = f"attachment{ext}" if ext else "attachment"

        size_bytes = int(size) if size is not None else None
        if size_bytes is not None and size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
            logger.warning(
                "Skipping oversized attachment filename=%s size=%s",
                filename,
                size_bytes,
            )
            return

        key = (attachment_id, filename)
        if key in seen:
            return
        seen.add(key)

        # Inline small parts may only have body.data (no attachmentId)
        provider_id = attachment_id
        if not provider_id and inline_data:
            provider_id = None

        results.append(
            FetchedAttachment(
                filename=filename,
                mime_type=mime.split(";")[0].strip() or None,
                size_bytes=size_bytes,
                provider_attachment_id=provider_id,
            )
        )

    _walk(payload)
    return results


def _filename_from_content_type(content_type: str) -> str | None:
    if not content_type:
        return None
    for token in content_type.split(";"):
        token = token.strip()
        if token.lower().startswith("name="):
            _, _, value = token.partition("=")
            return value.strip().strip('"') or None
    return None


def _filename_from_disposition(disposition: str) -> str | None:
    if not disposition:
        return None
    lower = disposition.lower()
    for token in disposition.split(";"):
        token = token.strip()
        if token.lower().startswith("filename*="):
            _, _, value = token.partition("=")
            value = value.strip().strip('"')
            if "''" in value:
                value = value.split("''", 1)[-1]
            return value or None
        if token.lower().startswith("filename="):
            _, _, value = token.partition("=")
            return value.strip().strip('"') or None
    if "filename" in lower:
        return None
    return None


def fetch_inline_attachment_bytes(payload: dict, filename: str) -> bytes | None:
    """Return bytes for a small inline part matching filename, if present in payload."""

    def _walk(part: dict) -> bytes | None:
        mime = part.get("mimeType", "")
        if mime.startswith("message/") and part.get("parts"):
            for sub in part.get("parts", []):
                found = _walk(sub)
                if found is not None:
                    return found
        headers = _part_headers_map(part)
        disp = headers.get("content-disposition", "")
        part_name = (
            part.get("filename")
            or headers.get("content-filename")
            or _filename_from_disposition(disp)
        )
        body = part.get("body", {})
        if part_name == filename and body.get("data") and not body.get("attachmentId"):
            return _decode_body_data(body["data"])
        for sub in part.get("parts", []):
            found = _walk(sub)
            if found is not None:
                return found
        return None

    return _walk(payload)


def _extract_body(payload: dict) -> tuple[str | None, str | None]:
    """Recursively walk MIME parts to extract text/plain and text/html."""
    text_parts: list[str] = []
    html_parts: list[str] = []

    def _walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data + "==").decode(
                "utf-8", errors="replace"
            )
            if mime == "text/plain":
                text_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)

        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)

    return (
        "\n".join(text_parts) if text_parts else None,
        "\n".join(html_parts) if html_parts else None,
    )


def list_thread_message_ids(
    account: EmailAccount,
    thread_id: str,
    db_session=None,
) -> list[str]:
    """Return Gmail message ids for every message in a thread."""
    creds = _get_credentials(account)
    access_token = _ensure_valid_token(account, creds, db_session)

    resp = httpx.get(
        f"{GMAIL_API_BASE}/threads/{thread_id}",
        params={"format": "minimal"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return [m["id"] for m in data.get("messages", []) if m.get("id")]
