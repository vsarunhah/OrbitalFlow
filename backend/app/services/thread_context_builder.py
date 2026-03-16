"""Build structured thread + job + user context for AI reply generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.llm.prompts import strip_quoted_replies
from app.models.contact import Contact, JobContact
from app.models.job import Job, JobThread
from app.models.message import Message

THREAD_CONTEXT_MAX_MESSAGES = 8
THREAD_MESSAGE_BODY_MAX_CHARS = 800


@dataclass
class ThreadMessageEntry:
    """Single message in thread context."""
    sender: str
    timestamp: str
    body_text: str


@dataclass
class ReplyContext:
    """Structured context for reply generation."""
    thread_messages: list[ThreadMessageEntry]
    job_company: str | None
    job_role: str | None
    job_stage: str
    recipient_info: str
    user_name: str
    tone: str
    user_instruction: str | None


def _resolve_thread_id(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
) -> str | None:
    """Resolve thread_id for context: from source message or from job_threads."""
    if source_message_id:
        msg = (
            db.query(Message)
            .filter(
                Message.id == source_message_id,
                Message.tenant_id == tenant_id,
            )
            .first()
        )
        if msg and msg.thread_id:
            return msg.thread_id
    rows = (
        db.query(JobThread.thread_id)
        .filter(
            JobThread.job_id == job_id,
            JobThread.tenant_id == tenant_id,
        )
        .all()
    )
    thread_ids = [r[0] for r in rows if r[0]]
    return thread_ids[0] if thread_ids else None


def _last_n_messages(
    db: Session,
    tenant_id: uuid.UUID,
    thread_id: str,
    n: int,
) -> list[Message]:
    """Return last n messages in thread, chronological order (oldest to newest)."""
    all_in_thread = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.thread_id == thread_id,
        )
        .order_by(Message.date_header.asc().nullslast())
        .all()
    )
    return all_in_thread[-n:] if len(all_in_thread) > n else all_in_thread


def _format_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return "(no date)"
    return dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)


def build_reply_context(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
    tone: str,
    user_instruction: str | None,
    user_email: str | None,
) -> ReplyContext:
    """
    Build structured context for reply generation: thread (last N messages),
    job, recipient info, user name (email), tone, user instruction.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise ValueError("Job not found")

    thread_id = _resolve_thread_id(db, tenant_id, job_id, source_message_id)
    thread_messages: list[ThreadMessageEntry] = []
    if thread_id:
        messages = _last_n_messages(
            db, tenant_id, thread_id, THREAD_CONTEXT_MAX_MESSAGES
        )
        for msg in messages:
            raw = (msg.body_text or "").strip()
            body = strip_quoted_replies(raw)
            if len(body) > THREAD_MESSAGE_BODY_MAX_CHARS:
                body = body[:THREAD_MESSAGE_BODY_MAX_CHARS] + "\n[...truncated...]"
            thread_messages.append(
                ThreadMessageEntry(
                    sender=msg.from_address or "(unknown)",
                    timestamp=_format_timestamp(msg.date_header),
                    body_text=body or "(no body)",
                )
            )

    job_contacts = (
        db.query(Contact, JobContact)
        .join(JobContact, JobContact.contact_id == Contact.id)
        .filter(
            JobContact.job_id == job_id,
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

    user_name = (user_email or "User").strip() or "User"
    tone_normalized = (tone or "professional").lower().strip()
    if tone_normalized not in (
        "professional",
        "warm",
        "concise",
        "enthusiastic",
        "direct",
    ):
        tone_normalized = "professional"

    return ReplyContext(
        thread_messages=thread_messages,
        job_company=job.company,
        job_role=job.role,
        job_stage=job.current_stage,
        recipient_info=recipient_info,
        user_name=user_name,
        tone=tone_normalized,
        user_instruction=user_instruction.strip() if user_instruction else None,
    )
