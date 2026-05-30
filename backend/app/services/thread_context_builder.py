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
from app.models.user import User
from app.services.user_profile import get_or_create_profile, profile_summary_for_prompt

# Include every message in the thread; cap total body text for LLM context size.
THREAD_MESSAGE_BODY_MAX_CHARS = 1200
THREAD_MESSAGE_BODY_MIN_CHARS = 100
THREAD_TOTAL_BODY_BUDGET_CHARS = 32_000


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
    user_timezone: str | None
    user_profile_summary: str
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


def _all_messages_in_thread(
    db: Session,
    tenant_id: uuid.UUID,
    thread_id: str,
) -> list[Message]:
    """Return all messages in thread, chronological order (oldest to newest)."""
    return (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.thread_id == thread_id,
        )
        .order_by(Message.date_header.asc().nullslast(), Message.id.asc())
        .all()
    )


def _truncate_body(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return "(no body)"
    suffix = "\n[...truncated...]"
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix if keep else "(no body)"


def _allocate_message_bodies(bodies: list[str]) -> list[str]:
    """
    Fit all thread bodies into THREAD_TOTAL_BODY_BUDGET_CHARS.
    Newer messages (end of list) keep more content when trimming is required.
    """
    if not bodies:
        return []
    n = len(bodies)
    per_msg_cap = [THREAD_MESSAGE_BODY_MAX_CHARS] * n
    if sum(min(len(b), per_msg_cap[i]) for i, b in enumerate(bodies)) <= THREAD_TOTAL_BODY_BUDGET_CHARS:
        return [_truncate_body(b, per_msg_cap[i]) for i, b in enumerate(bodies)]

    allocated = [0] * n
    budget = THREAD_TOTAL_BODY_BUDGET_CHARS
    for i in range(n - 1, -1, -1):
        if budget <= 0:
            break
        want = min(len(bodies[i]), THREAD_MESSAGE_BODY_MAX_CHARS)
        take = min(want, budget)
        if take < THREAD_MESSAGE_BODY_MIN_CHARS and len(bodies[i]) > 0:
            take = min(len(bodies[i]), THREAD_MESSAGE_BODY_MIN_CHARS, budget)
        allocated[i] = take
        budget -= take

    for i in range(n):
        if allocated[i] <= 0 and bodies[i].strip():
            allocated[i] = min(
                len(bodies[i]),
                THREAD_MESSAGE_BODY_MIN_CHARS,
                THREAD_TOTAL_BODY_BUDGET_CHARS,
            )
    return [_truncate_body(bodies[i], allocated[i]) for i in range(n)]


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
    user_id: uuid.UUID | None = None,
) -> ReplyContext:
    """
    Build structured context for reply generation: full thread (all messages),
    job, recipient info, user name (email), tone, user instruction.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise ValueError("Job not found")

    thread_id = _resolve_thread_id(db, tenant_id, job_id, source_message_id)
    thread_messages: list[ThreadMessageEntry] = []
    if thread_id:
        messages = _all_messages_in_thread(db, tenant_id, thread_id)
        stripped_bodies = [
            strip_quoted_replies((msg.body_text or "").strip()) or "(no body)"
            for msg in messages
        ]
        allocated_bodies = _allocate_message_bodies(stripped_bodies)
        for msg, body in zip(messages, allocated_bodies, strict=True):
            thread_messages.append(
                ThreadMessageEntry(
                    sender=msg.from_address or "(unknown)",
                    timestamp=_format_timestamp(msg.date_header),
                    body_text=body,
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

    user = None
    profile = None
    if user_id:
        user = (
            db.query(User)
            .filter(User.id == user_id, User.tenant_id == tenant_id)
            .first()
        )
        profile = get_or_create_profile(db, user_id, tenant_id)

    display = (profile.display_name if profile else None) or (user_email or "User")
    user_name = display.strip() or "User"
    user_timezone = profile.timezone if profile else None
    user_profile_summary = profile_summary_for_prompt(profile, user)

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
        user_timezone=user_timezone,
        user_profile_summary=user_profile_summary,
        tone=tone_normalized,
        user_instruction=user_instruction.strip() if user_instruction else None,
    )
