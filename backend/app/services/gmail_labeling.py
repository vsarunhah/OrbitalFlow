"""Gmail labeling service: create labels if missing, apply per-message labels.

Idempotency: Gmail's labels.list is checked before creation, and
messages.modify with addLabelIds is a no-op when the label is already present.
"""

from __future__ import annotations

import json
import logging
import uuid

import httpx
from sqlalchemy.orm import Session

from app.encryption import decrypt
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.models.tenant_settings import TenantSettings
from app.providers.gmail import GMAIL_API_BASE, _get_credentials, _ensure_valid_token

logger = logging.getLogger(__name__)

CATEGORY_TO_SETTINGS_FIELD = {
    "STATUS": "label_status",
    "RECRUITER": "label_recruiter",
    "ALERT": "label_alerts",
}


def get_or_create_tenant_settings(db: Session, tenant_id: uuid.UUID) -> TenantSettings:
    """Return existing settings or create defaults for a tenant."""
    settings = db.query(TenantSettings).filter(
        TenantSettings.tenant_id == tenant_id
    ).first()
    if settings is None:
        settings = TenantSettings(tenant_id=tenant_id)
        db.add(settings)
        db.flush()
    return settings


def ensure_label(access_token: str, label_name: str) -> str:
    """Return the Gmail label ID for *label_name*, creating it if absent."""
    labels = _list_labels(access_token)
    for lbl in labels:
        if lbl["name"] == label_name:
            return lbl["id"]

    return _create_label(access_token, label_name)


def apply_label(access_token: str, message_id: str, label_id: str) -> None:
    """Add *label_id* to a Gmail message. Idempotent (Gmail ignores dupes)."""
    url = f"{GMAIL_API_BASE}/messages/{message_id}/modify"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"addLabelIds": [label_id]},
        timeout=15,
    )
    resp.raise_for_status()
    logger.debug("Applied label %s to message %s", label_id, message_id)


def label_message_if_configured(
    db: Session,
    account: EmailAccount,
    message: Message,
    extraction: MessageExtraction,
) -> bool:
    """Apply a Gmail label based on extraction category, respecting tenant settings.

    Returns True if a label was applied, False otherwise.
    """
    if extraction.status != "completed":
        return False

    category = extraction.category
    if category not in CATEGORY_TO_SETTINGS_FIELD:
        logger.debug(
            "Category %s has no label mapping, skipping labeling for message_id=%s",
            category,
            message.id,
        )
        return False

    tenant_settings = get_or_create_tenant_settings(db, extraction.tenant_id)

    if not tenant_settings.labeling_enabled:
        logger.debug(
            "Labeling disabled for tenant_id=%s, skipping message_id=%s",
            extraction.tenant_id,
            message.id,
        )
        return False

    confidence = extraction.confidence or 0.0
    if confidence < tenant_settings.labeling_confidence_threshold:
        logger.info(
            "Confidence %.2f < threshold %.2f for message_id=%s, skipping label",
            confidence,
            tenant_settings.labeling_confidence_threshold,
            message.id,
        )
        return False

    label_name = getattr(tenant_settings, CATEGORY_TO_SETTINGS_FIELD[category])

    try:
        creds = _get_credentials(account)
        access_token = _ensure_valid_token(account, creds, db)

        label_id = ensure_label(access_token, label_name)
        apply_label(access_token, message.provider_msg_id, label_id)

        logger.info(
            "Labeled message_id=%s provider_msg_id=%s with '%s' (label_id=%s)",
            message.id,
            message.provider_msg_id,
            label_name,
            label_id,
        )
        return True

    except Exception:
        logger.exception(
            "Failed to apply Gmail label for message_id=%s (non-fatal)",
            message.id,
        )
        return False


def _list_labels(access_token: str) -> list[dict]:
    """Fetch all Gmail labels for the authenticated user."""
    url = f"{GMAIL_API_BASE}/labels"
    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("labels", [])


def _create_label(access_token: str, label_name: str) -> str:
    """Create a Gmail label and return its ID."""
    url = f"{GMAIL_API_BASE}/labels"
    body = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("Created Gmail label '%s' -> id=%s", label_name, data["id"])
    return data["id"]
