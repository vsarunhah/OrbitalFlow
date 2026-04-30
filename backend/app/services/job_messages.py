"""Load Gmail messages linked to jobs (events + thread membership)."""

from __future__ import annotations

import uuid
from typing import Dict, Iterable, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message


def load_messages_for_jobs(
    db: Session,
    tenant_id: uuid.UUID,
    jobs: Iterable[Job],
) -> Dict[uuid.UUID, List[Message]]:
    """Return job_id -> deduplicated messages for those jobs (same rules as timeline)."""
    job_list = list(jobs)
    if not job_list:
        return {}

    job_ids = [j.id for j in job_list]

    event_rows = (
        db.query(JobEvent.job_id, JobEvent.message_id)
        .filter(
            JobEvent.job_id.in_(job_ids),
            JobEvent.message_id.isnot(None),
        )
        .all()
    )
    job_to_msg_ids: Dict[uuid.UUID, set[uuid.UUID]] = {jid: set() for jid in job_ids}
    for job_id, message_id in event_rows:
        if message_id:
            job_to_msg_ids[job_id].add(message_id)

    thread_rows = (
        db.query(JobThread.job_id, JobThread.thread_id)
        .filter(
            JobThread.tenant_id == tenant_id,
            JobThread.job_id.in_(job_ids),
        )
        .all()
    )
    thread_ids: set[str] = set()
    thread_to_job_ids: Dict[str, List[uuid.UUID]] = {}
    for job_id, thread_id in thread_rows:
        if not thread_id:
            continue
        thread_ids.add(thread_id)
        thread_to_job_ids.setdefault(thread_id, []).append(job_id)

    all_message_ids: set[uuid.UUID] = set()
    for ids in job_to_msg_ids.values():
        all_message_ids.update(ids)

    messages_q = db.query(Message).filter(Message.tenant_id == tenant_id)
    if all_message_ids and thread_ids:
        messages_q = messages_q.filter(
            or_(Message.id.in_(all_message_ids), Message.thread_id.in_(thread_ids))
        )
    elif all_message_ids:
        messages_q = messages_q.filter(Message.id.in_(all_message_ids))
    elif thread_ids:
        messages_q = messages_q.filter(Message.thread_id.in_(thread_ids))
    else:
        messages_q = messages_q.filter(False)

    messages: List[Message] = messages_q.all()

    messages_by_job: Dict[uuid.UUID, List[Message]] = {jid: [] for jid in job_ids}
    for msg in messages:
        for job_id, msg_ids in job_to_msg_ids.items():
            if msg.id in msg_ids:
                messages_by_job[job_id].append(msg)

        if msg.thread_id and msg.thread_id in thread_to_job_ids:
            for job_id in thread_to_job_ids[msg.thread_id]:
                messages_by_job[job_id].append(msg)

    for job_id, msgs in messages_by_job.items():
        seen: set[uuid.UUID] = set()
        unique: List[Message] = []
        for m in msgs:
            if m.id in seen:
                continue
            seen.add(m.id)
            unique.append(m)
        messages_by_job[job_id] = unique

    return messages_by_job


def load_accounts_for_messages(
    db: Session,
    messages_by_job: Dict[uuid.UUID, list[Message]],
) -> Dict[uuid.UUID, EmailAccount]:
    account_ids: set[uuid.UUID] = set()
    for msgs in messages_by_job.values():
        for m in msgs:
            if m.account_id:
                account_ids.add(m.account_id)
    if not account_ids:
        return {}
    accounts = (
        db.query(EmailAccount)
        .filter(EmailAccount.id.in_(list(account_ids)))
        .all()
    )
    return {a.id: a for a in accounts}
