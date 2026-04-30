"""Per-user 'new incoming email' tracking for jobs (timeline last-seen)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job, JobTimelineReadState
from app.models.message import Message
from app.models.user import User
from app.services.job_messages import load_accounts_for_messages, load_messages_for_jobs
from app.services.job_processing import _parse_email_address
from app.services.next_action import infer_owner_email, message_timestamp

# Cap how many job IDs we scan when applying the unread-only list filter (per request).
MAX_UNREAD_FILTER_SCAN = 5000


def _effective_owner_email(
    messages: List[Message],
    accounts_by_id: Dict[uuid.UUID, EmailAccount],
    user_email_lower: str | None,
) -> str | None:
    owner = infer_owner_email(messages, accounts_by_id)
    if owner:
        return owner
    return user_email_lower


def count_incoming_after_last_seen(
    messages: List[Message],
    accounts_by_id: Dict[uuid.UUID, EmailAccount],
    user_email_lower: str | None,
    last_seen_at: datetime | None,
) -> int:
    """Inbound messages (not from account owner / logged-in user) after last_seen_at.

    If the user has never opened this job's timeline (last_seen_at is None), treat every
    non-owner inbound message as unread. That matches Gmail-style inbox expectations: a
    freshly ingested recruiter thread the user has never looked at should light up as new.
    """
    if last_seen_at is not None and last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)

    owner = _effective_owner_email(messages, accounts_by_id, user_email_lower)
    if not owner:
        return 0

    n = 0
    for msg in messages:
        _, from_email = _parse_email_address(msg.from_address or "")
        if not from_email or from_email == owner:
            continue
        if last_seen_at is None:
            n += 1
            continue
        ts = message_timestamp(msg)
        if ts > last_seen_at:
            n += 1
    return n


def load_last_seen_map(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_ids: List[uuid.UUID],
) -> Dict[uuid.UUID, datetime | None]:
    if not job_ids:
        return {}
    rows = (
        db.query(JobTimelineReadState)
        .filter(
            JobTimelineReadState.tenant_id == tenant_id,
            JobTimelineReadState.user_id == user_id,
            JobTimelineReadState.job_id.in_(job_ids),
        )
        .all()
    )
    found = {r.job_id: r.last_seen_at for r in rows}
    return {jid: found.get(jid) for jid in job_ids}


def load_needs_reply_dismissal_map(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_ids: List[uuid.UUID],
) -> Dict[uuid.UUID, uuid.UUID | None]:
    """Per-job message id: user dismissed needs-reply nudge for that inbound message."""
    if not job_ids:
        return {}
    rows = (
        db.query(JobTimelineReadState)
        .filter(
            JobTimelineReadState.tenant_id == tenant_id,
            JobTimelineReadState.user_id == user_id,
            JobTimelineReadState.job_id.in_(job_ids),
        )
        .all()
    )
    found = {r.job_id: r.needs_reply_dismissed_up_to_message_id for r in rows}
    return {jid: found.get(jid) for jid in job_ids}


def ordered_job_ids_with_unread_incoming(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ordered_job_ids: List[uuid.UUID],
) -> List[uuid.UUID]:
    """Preserve input order; return only job IDs with unread_incoming_count > 0."""
    if not ordered_job_ids:
        return []

    user_email_l = user_email_lower_for(db, tenant_id, user_id)
    out: List[uuid.UUID] = []
    batch_size = 100

    for i in range(0, len(ordered_job_ids), batch_size):
        chunk_ids = ordered_job_ids[i : i + batch_size]
        jobs = db.query(Job).filter(Job.id.in_(chunk_ids)).all()
        by_id = {j.id: j for j in jobs}
        ordered_chunk = [by_id[jid] for jid in chunk_ids if jid in by_id]
        if not ordered_chunk:
            continue

        messages_by_job = load_messages_for_jobs(db, tenant_id, ordered_chunk)
        accounts_by_id = load_accounts_for_messages(db, messages_by_job)
        last_seen_map = load_last_seen_map(db, tenant_id, user_id, chunk_ids)

        for jid in chunk_ids:
            job = by_id.get(jid)
            if not job:
                continue
            msgs = messages_by_job.get(jid, [])
            if (
                count_incoming_after_last_seen(
                    msgs,
                    accounts_by_id,
                    user_email_l,
                    last_seen_map.get(jid),
                )
                > 0
            ):
                out.append(jid)
    return out


def mark_timeline_unread(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job: Job,
) -> None:
    """Move last_seen just before the latest inbound message so it counts as unread again."""
    messages_by_job = load_messages_for_jobs(db, tenant_id, [job])
    msgs = messages_by_job.get(job.id, [])
    accounts_by_id = load_accounts_for_messages(db, messages_by_job)
    user_email_l = user_email_lower_for(db, tenant_id, user_id)
    owner = _effective_owner_email(msgs, accounts_by_id, user_email_l)

    q = db.query(JobTimelineReadState).filter(
        JobTimelineReadState.tenant_id == tenant_id,
        JobTimelineReadState.user_id == user_id,
        JobTimelineReadState.job_id == job.id,
    )

    if not owner:
        q.delete(synchronize_session=False)
        return

    inbound_ts: List[datetime] = []
    for msg in msgs:
        _, from_email = _parse_email_address(msg.from_address or "")
        if not from_email or from_email == owner:
            continue
        inbound_ts.append(message_timestamp(msg))

    if not inbound_ts:
        q.delete(synchronize_session=False)
        return

    max_ts = max(inbound_ts)
    rewind = max_ts - timedelta(microseconds=1)

    row = q.first()
    if row:
        row.last_seen_at = rewind
    else:
        db.add(
            JobTimelineReadState(
                tenant_id=tenant_id,
                user_id=user_id,
                job_id=job.id,
                last_seen_at=rewind,
            )
        )


def upsert_timeline_last_seen(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    now = datetime.now(timezone.utc)
    row = (
        db.query(JobTimelineReadState)
        .filter(
            JobTimelineReadState.tenant_id == tenant_id,
            JobTimelineReadState.user_id == user_id,
            JobTimelineReadState.job_id == job_id,
        )
        .first()
    )
    if row:
        row.last_seen_at = now
    else:
        db.add(
            JobTimelineReadState(
                tenant_id=tenant_id,
                user_id=user_id,
                job_id=job_id,
                last_seen_at=now,
            )
        )


def set_needs_reply_dismissed_for_job(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job: Job,
    message_id: uuid.UUID,
) -> None:
    """Store which inbound message the user marked 'no reply needed' for (must exist)."""
    row = (
        db.query(JobTimelineReadState)
        .filter(
            JobTimelineReadState.tenant_id == tenant_id,
            JobTimelineReadState.user_id == user_id,
            JobTimelineReadState.job_id == job.id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if row:
        row.needs_reply_dismissed_up_to_message_id = message_id
    else:
        db.add(
            JobTimelineReadState(
                tenant_id=tenant_id,
                user_id=user_id,
                job_id=job.id,
                last_seen_at=now,
                needs_reply_dismissed_up_to_message_id=message_id,
            )
        )


def user_email_lower_for(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    u = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == tenant_id)
        .first()
    )
    if not u or not u.email:
        return None
    return u.email.strip().lower()
