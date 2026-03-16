"""Extraction service: orchestrates LLM call, validates output, persists result.

Security invariants:
 - Decrypted API keys live only in local variables, never logged.
 - Email bodies are truncated before sending to the LLM.
 - Only a short snippet of raw LLM response is stored for debugging.
"""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.encryption import decrypt
from app.llm.base import LlmResponse
from app.llm.factory import get_llm_client
from app.llm.prompts import EXTRACTION_SYSTEM_PROMPT, build_user_content
from app.models.llm_key import LlmKey
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.schemas.extraction import Category, EventType, ExtractionResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RAW_SNIPPET_LIMIT = 500
# ALERT with no job listings and confidence below this is reclassified to OTHER
ALERT_OVERRIDE_CONFIDENCE_THRESHOLD = 0.85


def run_extraction(db: Session, message_id: uuid.UUID, tenant_id: uuid.UUID) -> MessageExtraction:
    """Run LLM extraction for a single message. Returns the persisted extraction row."""
    extraction = MessageExtraction(
        tenant_id=tenant_id,
        message_id=message_id,
        status="pending",
    )
    db.add(extraction)

    llm_key_row = _get_llm_key(db, tenant_id)
    if llm_key_row is None:
        extraction.status = "failed"
        extraction.error_reason = "llm_key_not_configured"
        _update_message_status(db, message_id, "extraction_failed")
        db.commit()
        logger.warning(
            "No LLM key configured for tenant_id=%s, extraction failed for message_id=%s",
            tenant_id,
            message_id,
        )
        return extraction

    try:
        api_key = decrypt(llm_key_row.encrypted_key)
    except Exception:
        extraction.status = "failed"
        extraction.error_reason = "llm_key_decryption_failed"
        _update_message_status(db, message_id, "extraction_failed")
        db.commit()
        logger.exception(
            "Failed to decrypt LLM key for tenant_id=%s", tenant_id
        )
        return extraction

    message = db.query(Message).filter(Message.id == message_id).first()
    if message is None:
        extraction.status = "failed"
        extraction.error_reason = "message_not_found"
        db.commit()
        return extraction

    user_content = build_user_content(
        message.subject, message.body_text, message.from_address
    )

    client = get_llm_client(llm_key_row.provider, api_key)
    extraction.llm_provider = client.provider_name

    result: ExtractionResult | None = None
    llm_response: LlmResponse | None = None
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm_response = client.chat_json(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_content=user_content,
            )
            extraction.raw_response_snippet = llm_response.raw_text[:RAW_SNIPPET_LIMIT]
            extraction.llm_model = llm_response.model
            extraction.prompt_tokens = llm_response.prompt_tokens
            extraction.completion_tokens = llm_response.completion_tokens

            parsed = json.loads(llm_response.raw_text)
            result = ExtractionResult.model_validate(parsed)
            break

        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "LLM output validation failed (attempt %d/%d) message_id=%s: %s",
                attempt,
                MAX_RETRIES,
                message_id,
                last_error,
            )
            continue

        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "LLM API call failed (attempt %d/%d) message_id=%s",
                attempt,
                MAX_RETRIES,
                message_id,
            )
            continue

    if result is None:
        extraction.status = "failed"
        extraction.error_reason = f"extraction_failed_after_{MAX_RETRIES}_attempts: {last_error}"
        _update_message_status(db, message_id, "extraction_failed")
        db.commit()
        return extraction

    # Post-extraction safeguard: ALERT with no job listings and low confidence -> OTHER
    if (
        result.category == Category.ALERT
        and not result.jobs
        and result.confidence < ALERT_OVERRIDE_CONFIDENCE_THRESHOLD
    ):
        result.category = Category.OTHER
        result.event_type = EventType.NONE
        logger.info(
            "Override ALERT -> OTHER for message_id=%s (empty jobs, confidence=%.2f)",
            message_id,
            result.confidence,
        )

    # Post-extraction safeguard: LinkedIn message-notification emails must not be RECRUITER
    _from = (message.from_address or "").strip().lower()
    if (
        result.category == Category.RECRUITER
        and ("messaging-digest-noreply@linkedin.com" in _from or "noreply@linkedin.com" in _from)
    ):
        result.category = Category.OTHER
        result.event_type = EventType.NONE
        logger.info(
            "Override RECRUITER -> OTHER for message_id=%s (LinkedIn message notification from %s)",
            message_id,
            _from[:80],
        )

    extraction.category = result.category.value
    extraction.event_type = result.event_type.value
    extraction.company = result.company
    extraction.role = result.role
    extraction.req_id = result.req_id
    extraction.contacts_json = json.dumps(
        [c.model_dump(exclude_none=True) for c in result.contacts]
    )
    extraction.confidence = result.confidence
    extraction.rationale = result.rationale
    useful_jobs = [j for j in result.jobs if j.company or j.role]
    if useful_jobs:
        extraction.alert_jobs_json = json.dumps(
            [j.model_dump(exclude_none=True) for j in useful_jobs]
        )
    extraction.status = "completed"

    message.category = result.category.value
    message.extraction_status = "completed"

    db.commit()

    logger.info(
        "Extraction completed message_id=%s category=%s event_type=%s confidence=%.2f",
        message_id,
        result.category.value,
        result.event_type.value,
        result.confidence,
    )
    return extraction


def _get_llm_key(db: Session, tenant_id: uuid.UUID) -> LlmKey | None:
    return db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).first()


def _update_message_status(db: Session, message_id: uuid.UUID, status: str) -> None:
    msg = db.query(Message).filter(Message.id == message_id).first()
    if msg:
        msg.extraction_status = status
