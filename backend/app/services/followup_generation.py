"""Generate follow-up email suggestions when a job is stalled. Uses tenant BYOK LLM."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.encryption import decrypt
from app.llm.base import LlmResponse
from app.llm.factory import get_llm_client
from app.llm.prompts import (
    FOLLOW_UP_GENERATION_SYSTEM_PROMPT,
    build_followup_user_content,
    strip_quoted_replies,
)
from app.models.job import Job
from app.models.contact import Contact, JobContact
from app.models.llm_key import LlmKey
from app.schemas.draft import DraftReplyResult
from app.services.thread_context_builder import (
    THREAD_CONTEXT_MAX_MESSAGES,
    THREAD_MESSAGE_BODY_MAX_CHARS,
    _format_timestamp,
    _last_n_messages,
    _resolve_thread_id,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _build_followup_context(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    user_email: str | None,
) -> dict:
    """Build context dict for follow-up prompt: job, recipient, thread, time since activity."""
    thread_id = _resolve_thread_id(db, tenant_id, job.id, None)
    thread_messages: list[dict] = []
    time_since_days: int | None = None
    now = datetime.now(timezone.utc)

    if thread_id:
        messages = _last_n_messages(db, tenant_id, thread_id, THREAD_CONTEXT_MAX_MESSAGES)
        for msg in messages:
            raw = (msg.body_text or "").strip()
            body = strip_quoted_replies(raw)
            if len(body) > THREAD_MESSAGE_BODY_MAX_CHARS:
                body = body[:THREAD_MESSAGE_BODY_MAX_CHARS] + "\n[...truncated...]"
            thread_messages.append({
                "sender": msg.from_address or "(unknown)",
                "timestamp": _format_timestamp(msg.date_header),
                "body_text": body or "(no body)",
            })
        if messages:
            last_msg = messages[-1]
            ts = last_msg.date_header or last_msg.created_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_since_days = (now - ts).days

    if time_since_days is None and job.last_activity:
        la = job.last_activity
        if la.tzinfo is None:
            la = la.replace(tzinfo=timezone.utc)
        time_since_days = (now - la).days

    job_contacts = (
        db.query(Contact, JobContact)
        .join(JobContact, JobContact.contact_id == Contact.id)
        .filter(
            JobContact.job_id == job.id,
            JobContact.tenant_id == tenant_id,
        )
        .all()
    )
    recipient_parts = []
    for contact, jc in job_contacts:
        name = contact.name or contact.email
        recipient_parts.append(f"- {name} <{contact.email}> ({jc.role})")
    recipient_info = (
        "\n".join(recipient_parts)
        if recipient_parts
        else "Recipient not specified (use thread To/From)."
    )

    return {
        "thread_messages": thread_messages,
        "job_company": job.company,
        "job_role": job.role,
        "job_stage": job.current_stage,
        "recipient_info": recipient_info,
        "user_name": (user_email or "User").strip() or "User",
        "time_since_last_activity_days": time_since_days,
    }


def generate_followup_suggestion(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    user_email: str | None = None,
) -> DraftReplyResult:
    """
    Generate a follow-up email suggestion for a stalled job.
    Returns subject, body, tone, confidence. Raises ValueError if no LLM key, job not found, or generation fails.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise ValueError("Job not found")

    context = _build_followup_context(db, tenant_id, job, user_email)
    user_content = build_followup_user_content(context)

    llm_key_row = db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).first()
    if not llm_key_row:
        raise ValueError("LLM key not configured for this tenant")

    try:
        api_key = decrypt(llm_key_row.encrypted_key)
    except Exception:
        logger.exception("Failed to decrypt LLM key for tenant_id=%s", tenant_id)
        raise ValueError("LLM key decryption failed")

    client = get_llm_client(llm_key_row.provider, api_key)
    result: DraftReplyResult | None = None
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm_response: LlmResponse = client.chat_json(
                system_prompt=FOLLOW_UP_GENERATION_SYSTEM_PROMPT,
                user_content=user_content,
                temperature=0.3,
                max_tokens=1024,
            )
            raw = llm_response.raw_text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            parsed = json.loads(raw)
            result = DraftReplyResult.model_validate(parsed)
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "Follow-up generation parse failed (attempt %d/%d) job_id=%s: %s",
                attempt, MAX_RETRIES, job_id, last_error,
            )
            continue
        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "Follow-up generation LLM call failed (attempt %d/%d) job_id=%s",
                attempt, MAX_RETRIES, job_id,
            )
            continue

    if result is None:
        raise ValueError(
            f"Follow-up generation failed after {MAX_RETRIES} attempts: {last_error or 'unknown'}"
        )

    return result
