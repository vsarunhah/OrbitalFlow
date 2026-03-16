"""Abstract interfaces for email providers and change sources.

EmailProvider: fetches a single message by ID from the upstream provider.
ChangeSource: returns message references that changed since the last cursor.

Both are designed to be swappable (e.g. Gmail polling -> Pub/Sub) without
touching the ingestion pipeline.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.models.email_account import EmailAccount


@dataclass(frozen=True)
class MessageRef:
    """Lightweight reference to a provider message (no body yet)."""
    provider_msg_id: str
    thread_id: str | None = None


@dataclass(frozen=True)
class ChangeResult:
    """Return type of ChangeSource.get_changes."""
    refs: list[MessageRef] = field(default_factory=list)
    new_cursor: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    """Result of sending a message via EmailProvider.send_message (Gmail)."""
    provider_message_id: str
    thread_id: str | None


@dataclass(frozen=True)
class FetchedMessage:
    """Parsed message returned by EmailProvider.fetch_message."""
    provider_msg_id: str
    thread_id: str | None
    subject: str | None
    from_address: str | None
    to_addresses: str | None
    date_header: str | None
    body_text: str | None
    body_html: str | None
    headers_json: str
    raw_payload_json: str
    label_ids_json: str | None


class EmailProvider(abc.ABC):
    @abc.abstractmethod
    def fetch_message(
        self, account: EmailAccount, message_id: str
    ) -> FetchedMessage:
        """Fetch a full message from the provider."""
        ...


class ChangeSource(abc.ABC):
    @abc.abstractmethod
    def get_changes(
        self, account: EmailAccount, cursor: dict[str, Any]
    ) -> ChangeResult:
        """Return message refs that changed since *cursor*, plus a new cursor."""
        ...
