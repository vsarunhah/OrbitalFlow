"""Force-index a Gmail link into a specific job (or create a new job)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.providers.gmail import GmailProvider, list_thread_message_ids
from app.schemas.job import JobStage
from app.services.gmail_link import ParsedGmailLink, parse_gmail_link
from app.services.job_processing import bump_job_last_activity_if_newer, message_activity_at

logger = logging.getLogger(__name__)


def _gmail_fetch_error(exc: httpx.HTTPStatusError, *, kind: str) -> ForceIndexError:
    """Map Gmail HTTP errors to user-facing import failures."""
    status_code = exc.response.status_code
    if status_code in (403, 404):
        return ForceIndexError(
            f"{kind} not found in your connected Gmail account."
        )
    if status_code == 400:
        return ForceIndexError(
            f"{kind} not found. Copy the full Gmail URL from the address bar "
            "(#inbox/… or #all/…) for an email in your connected inbox."
        )
    return ForceIndexError(
        f"Gmail API error while fetching the {kind.lower()}. Try reconnecting Gmail."
    )


@dataclass(frozen=True)
class ForceIndexResult:
    job_id: uuid.UUID
    job_created: bool
    messages_ingested: int
    messages_linked: int
    thread_ids: list[str]


class ForceIndexError(Exception):
    """User-facing error during force index."""


def force_index_email_link(
    db: Session,
    tenant_id: uuid.UUID,
    email_url: str,
    *,
    job_id: uuid.UUID | None = None,
    company: str | None = None,
    role: str | None = None,
) -> ForceIndexResult:
    """Fetch/ingest Gmail messages from a link and attach them to a job."""
    try:
        parsed = parse_gmail_link(email_url)
    except ValueError as exc:
        raise ForceIndexError(str(exc)) from exc

    accounts = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.tenant_id == tenant_id,
            EmailAccount.status == "active",
        )
        .order_by(EmailAccount.created_at.asc())
        .all()
    )
    if not accounts:
        raise ForceIndexError(
            "No connected Gmail account. Connect Gmail in Settings first."
        )

    account, provider_msg_ids, thread_ids = _resolve_provider_message_ids(
        accounts, parsed
    )
    if not provider_msg_ids:
        raise ForceIndexError("No messages found for that Gmail link.")

    messages, ingested_count = _ingest_messages(db, account, provider_msg_ids)
    if not messages:
        raise ForceIndexError(
            "Could not ingest messages. Check that the link is from your connected inbox."
        )

    thread_ids = sorted({tid for tid in thread_ids if tid} | {m.thread_id for m in messages if m.thread_id})

    job, created = _resolve_target_job(
        db,
        tenant_id,
        job_id=job_id,
        company=company,
        role=role,
        messages=messages,
    )

    linked_count = _force_link_to_job(db, tenant_id, job, messages, thread_ids)
    db.commit()
    db.refresh(job)

    logger.info(
        "Force indexed email link job_id=%s created=%s ingested=%d linked=%d threads=%s",
        job.id,
        created,
        ingested_count,
        linked_count,
        thread_ids,
    )
    return ForceIndexResult(
        job_id=job.id,
        job_created=created,
        messages_ingested=ingested_count,
        messages_linked=linked_count,
        thread_ids=thread_ids,
    )


def _resolve_provider_message_ids(
    accounts: list[EmailAccount],
    parsed: ParsedGmailLink,
) -> tuple[EmailAccount, list[str], list[str]]:
    """Resolve full thread message ids via Gmail API."""
    if parsed.thread_id:
        for account in accounts:
            try:
                ids = list_thread_message_ids(account, parsed.thread_id, db_session=None)
                if ids:
                    return account, ids, [parsed.thread_id]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 404):
                    continue
                raise _gmail_fetch_error(exc, kind="Thread") from exc
        raise ForceIndexError(
            "Thread not found in your connected Gmail account."
        )

    assert parsed.provider_msg_id
    last_error: Exception | None = None
    for account in accounts:
        try:
            provider = GmailProvider(db_session=None)
            fetched = provider.fetch_message(account, parsed.provider_msg_id)
            thread_id = fetched.thread_id
            if thread_id:
                ids = list_thread_message_ids(account, thread_id, db_session=None)
                if ids:
                    return account, ids, [thread_id]
            return account, [parsed.provider_msg_id], [thread_id] if thread_id else []
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in (403, 404):
                continue
            raise _gmail_fetch_error(exc, kind="Message") from exc
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        logger.warning("Force index fetch failed: %s", last_error)
    raise ForceIndexError(
        "Message not found in your connected Gmail account."
    )


def _ingest_messages(
    db: Session,
    account: EmailAccount,
    provider_msg_ids: list[str],
) -> tuple[list[Message], int]:
    """Ensure each provider message id exists locally; ingest missing ones."""
    from app.workers.jobs import process_message

    account_id_str = str(account.id)
    seen: set[str] = set()
    messages: list[Message] = []
    ingested = 0

    for provider_msg_id in provider_msg_ids:
        if provider_msg_id in seen:
            continue
        seen.add(provider_msg_id)

        existing = (
            db.query(Message)
            .filter(
                Message.account_id == account.id,
                Message.provider_msg_id == provider_msg_id,
            )
            .first()
        )
        if existing:
            messages.append(existing)
            continue

        result = process_message(account_id_str, provider_msg_id)
        if result.get("status") == "ok":
            ingested += 1
            msg = db.query(Message).filter(Message.id == uuid.UUID(result["message_id"])).first()
            if msg:
                messages.append(msg)
        elif result.get("status") == "skipped" and result.get("reason") == "duplicate":
            dup = (
                db.query(Message)
                .filter(
                    Message.account_id == account.id,
                    Message.provider_msg_id == provider_msg_id,
                )
                .first()
            )
            if dup:
                messages.append(dup)

    return messages, ingested


def _resolve_target_job(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    job_id: uuid.UUID | None,
    company: str | None,
    role: str | None,
    messages: list[Message],
) -> tuple[Job, bool]:
    if job_id is not None:
        job = (
            db.query(Job)
            .filter(Job.id == job_id, Job.tenant_id == tenant_id)
            .first()
        )
        if not job:
            raise ForceIndexError("Selected job not found.")
        return job, False

    resolved_company = company
    resolved_role = role
    if not resolved_company or not resolved_role:
        extraction = (
            db.query(MessageExtraction)
            .filter(
                MessageExtraction.message_id.in_([m.id for m in messages]),
                MessageExtraction.status == "completed",
            )
            .order_by(MessageExtraction.created_at.desc())
            .first()
        )
        if extraction:
            if not resolved_company:
                resolved_company = extraction.company
            if not resolved_role:
                resolved_role = extraction.role

    if not resolved_company and messages:
        subject = next((m.subject for m in messages if m.subject), None)
        if subject:
            resolved_company = subject[:255]

    job = Job(
        tenant_id=tenant_id,
        company=resolved_company,
        role=resolved_role,
        current_stage=JobStage.SOURCED.value,
        last_activity=message_activity_at(messages[-1]),
    )
    db.add(job)
    db.flush()
    return job, True


def _force_link_to_job(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    messages: list[Message],
    thread_ids: list[str],
) -> int:
    """Reassign thread links and job events so messages appear on the target job."""
    linked = 0

    for thread_id in thread_ids:
        existing = (
            db.query(JobThread)
            .filter(
                JobThread.tenant_id == tenant_id,
                JobThread.thread_id == thread_id,
            )
            .first()
        )
        if existing:
            if existing.job_id != job.id:
                existing.job_id = job.id
                linked += 1
        else:
            db.add(
                JobThread(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    thread_id=thread_id,
                )
            )
            linked += 1

    msg_ids = [m.id for m in messages]
    if msg_ids:
        db.query(JobEvent).filter(
            JobEvent.tenant_id == tenant_id,
            JobEvent.message_id.in_(msg_ids),
            JobEvent.job_id != job.id,
        ).update({"job_id": job.id}, synchronize_session=False)

        existing_on_job = {
            row[0]
            for row in db.query(JobEvent.message_id)
            .filter(
                JobEvent.job_id == job.id,
                JobEvent.message_id.in_(msg_ids),
            )
            .all()
        }

        for msg in messages:
            if msg.id in existing_on_job:
                continue
            db.add(
                JobEvent(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    message_id=msg.id,
                    source="manual_import",
                    rationale="Imported from Gmail link",
                    stage_before=job.current_stage,
                    stage_after=job.current_stage,
                )
            )
            linked += 1
            existing_on_job.add(msg.id)

    for msg in messages:
        bump_job_last_activity_if_newer(job, message_activity_at(msg))

    db.flush()
    return linked
