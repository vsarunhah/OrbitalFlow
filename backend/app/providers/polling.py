"""Polling-based ChangeSource for Gmail.

Lists messages since (cursor_timestamp - lookback_window) using the Gmail
messages.list endpoint with an `after:YYYY/MM/DD` query (Gmail's documented
format). Returns MessageRefs for each result and a new cursor with the updated
timestamp.

Swappable to Pub/Sub by implementing ChangeSource differently.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.encryption import decrypt
from app.models.email_account import EmailAccount
from app.providers.base import ChangeResult, ChangeSource, MessageRef
from app.providers.gmail import GMAIL_API_BASE, _ensure_valid_token, TokenRefreshError

logger = logging.getLogger(__name__)

MAX_PAGES = 20

# Gmail labels we never ingest (unsent drafts, spam, trash).
_EXCLUDED_SYNC_LABELS = ("drafts", "spam", "trash")


def _after_query_from_epoch(epoch_sec: int) -> str:
    """Format epoch seconds as Gmail's documented after:YYYY/MM/DD query."""
    dt = datetime.fromtimestamp(epoch_sec, tz=timezone.utc)
    return dt.strftime("%Y/%m/%d")


def build_sync_query(after_date: str) -> str:
    """Gmail search query for sync: date window minus drafts/spam/trash."""
    exclusions = " ".join(f"-in:{label}" for label in _EXCLUDED_SYNC_LABELS)
    return f"after:{after_date} {exclusions}".strip()


class PollingChangeSource(ChangeSource):
    """Poll Gmail messages.list for new messages since last cursor."""

    def __init__(self, db_session=None):
        self._db = db_session

    def get_changes(
        self,
        account: EmailAccount,
        cursor: dict[str, Any],
        after_epoch_override: int | None = None,
    ) -> ChangeResult:
        logger.info(
            "Polling changes for account_id=%s cursor=%s override=%s",
            account.id,
            {k: v for k, v in cursor.items() if k != "access_token"},
            after_epoch_override,
        )

        creds = json.loads(decrypt(account.oauth_encrypted))
        access_token = _ensure_valid_token(account, creds, self._db)

        after_epoch = after_epoch_override if after_epoch_override is not None else _compute_after_epoch(cursor)
        logger.info(
            "Querying messages after epoch=%s for account_id=%s",
            after_epoch,
            account.id,
        )

        refs: list[MessageRef] = []
        page_token: str | None = None

        after_query = _after_query_from_epoch(after_epoch)
        sync_query = build_sync_query(after_query)
        logger.info(
            "Gmail sync query: %s (from epoch=%s)",
            sync_query,
            after_epoch,
        )
        for page_num in range(MAX_PAGES):
            params: dict[str, Any] = {
                "q": sync_query,
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = httpx.get(
                f"{GMAIL_API_BASE}/messages",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if resp.status_code == 401:
                raise PermissionError(
                    f"Gmail API returned 401 Unauthorized for account_id={account.id}. "
                    "Reconnect the account in Settings (token may be expired or revoked)."
                ) from None
            resp.raise_for_status()
            data = resp.json()

            for msg in data.get("messages", []):
                refs.append(
                    MessageRef(
                        provider_msg_id=msg["id"],
                        thread_id=msg.get("threadId"),
                    )
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            logger.debug(
                "Page %d fetched, %d refs so far for account_id=%s",
                page_num + 1,
                len(refs),
                account.id,
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        new_cursor = {
            "last_polled_at": now_iso,
            "history_id": cursor.get("history_id"),
        }

        logger.info(
            "Poll complete for account_id=%s: %d message refs found",
            account.id,
            len(refs),
        )
        return ChangeResult(refs=refs, new_cursor=new_cursor)


def _compute_after_epoch(cursor: dict[str, Any]) -> int:
    """Determine the `after:` epoch based on cursor + lookback."""
    last_polled = cursor.get("last_polled_at")
    lookback = timedelta(minutes=settings.sync_lookback_minutes)

    if last_polled:
        try:
            last_dt = datetime.fromisoformat(last_polled)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            start = last_dt - lookback
        except (ValueError, TypeError):
            logger.warning("Invalid last_polled_at in cursor, using lookback from now")
            start = datetime.now(timezone.utc) - lookback
    else:
        start = datetime.now(timezone.utc) - lookback

    return int(start.timestamp())
