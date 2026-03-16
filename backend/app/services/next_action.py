"""Next-action intelligence for jobs.

Given a set of jobs, their related messages, and the account owner email,
compute a single "next action" per job based on simple, deterministic rules:

- If the last message in the thread is from the recruiter (not the owner):
  - If that message is at least NEEDS_REPLY_DAYS old -> "Follow up with recruiter..."
  - Otherwise -> "You haven't replied yet"
- If there has been no activity for GHOSTED_DAYS or more (and stage is non-terminal):
  - "Ghosted?"

Computation is done on read (list/detail/timeline) and never mutates DB state.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message
from app.schemas.job import JobStage
from app.services.job_processing import _parse_email_address


NEEDS_REPLY_DAYS = 6
GHOSTED_DAYS = 14


SCHEDULING_DOMAINS = (
    "calendly.com",
    "goodtime.io",
    "calendar.google.com",
    "outlook.office365.com",
    "outlook.live.com",
)


@dataclass
class NextActionData:
    """Lightweight structure returned by the service.

    Routers convert this into the public Pydantic NextAction schema.
    """

    type: str
    label: str
    due_at: Optional[datetime] = None
    scheduling_link: Optional[str] = None


def compute_next_actions_for_jobs(
    db: Session,
    tenant_id: uuid.UUID,
    jobs: Iterable[Job],
) -> Dict[uuid.UUID, Optional[NextActionData]]:
    """Return a mapping of job_id -> NextActionData | None."""
    job_list = list(jobs)
    if not job_list:
        return {}

    job_ids = [j.id for j in job_list]

    # 1) Collect event-linked message_ids per job
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

    # 2) Collect thread_ids per job
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

    # 3) Fetch all relevant messages in one query
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
        messages_q = messages_q.filter(False)  # no messages at all

    messages: List[Message] = messages_q.all()

    # 4) Attach messages back to jobs
    messages_by_job: Dict[uuid.UUID, List[Message]] = {jid: [] for jid in job_ids}
    for msg in messages:
        # via explicit event link
        for job_id, msg_ids in job_to_msg_ids.items():
            if msg.id in msg_ids:
                messages_by_job[job_id].append(msg)

        # via thread association
        if msg.thread_id and msg.thread_id in thread_to_job_ids:
            for job_id in thread_to_job_ids[msg.thread_id]:
                messages_by_job[job_id].append(msg)

    # De-duplicate messages per job
    for job_id, msgs in messages_by_job.items():
        seen: set[uuid.UUID] = set()
        unique: List[Message] = []
        for m in msgs:
            if m.id in seen:
                continue
            seen.add(m.id)
            unique.append(m)
        messages_by_job[job_id] = unique

    # 5) Load owner emails (by account_id) once for all messages
    account_ids: set[uuid.UUID] = set()
    for msgs in messages_by_job.values():
        for m in msgs:
            if m.account_id:
                account_ids.add(m.account_id)

    accounts_by_id: Dict[uuid.UUID, EmailAccount] = {}
    if account_ids:
        accounts = (
            db.query(EmailAccount)
            .filter(EmailAccount.id.in_(list(account_ids)))
            .all()
        )
        accounts_by_id = {a.id: a for a in accounts}

    # 6) Compute next action per job
    result: Dict[uuid.UUID, Optional[NextActionData]] = {}
    now = datetime.now(timezone.utc)

    for job in job_list:
        msgs = messages_by_job.get(job.id, [])
        owner_email = _infer_owner_email(msgs, accounts_by_id)
        action = _compute_next_action_for_job(job, msgs, owner_email, now)
        result[job.id] = action

    return result


def _infer_owner_email(
    messages: List[Message],
    accounts_by_id: Dict[uuid.UUID, EmailAccount],
) -> Optional[str]:
    """Best-effort guess of the user's own email address for a job."""
    for msg in messages:
        account = accounts_by_id.get(msg.account_id)
        if account and account.email_address:
            return account.email_address.strip().lower()
    return None


def _message_timestamp(msg: Message) -> datetime:
    """Choose the best timestamp for ordering messages chronologically."""
    ts = msg.date_header or msg.created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _find_scheduling_link(msg: Message) -> Optional[str]:
    """Extract the first scheduling-related URL from a message body, if any."""
    # Very lightweight URL finder; good enough for common cases.
    text_parts: List[str] = []
    if msg.body_text:
        text_parts.append(msg.body_text)
    if msg.body_html:
        text_parts.append(msg.body_html)
    if not text_parts:
        return None

    combined = " ".join(text_parts)
    url_pattern = re.compile(r"https?://[^\s\")'>]+", re.IGNORECASE)
    for match in url_pattern.finditer(combined):
        url = match.group(0)
        if any(domain in url for domain in SCHEDULING_DOMAINS):
            return url
    return None


def suggest_followup_for_next_action(na_data: Optional[NextActionData]) -> bool:
    """True when we should offer 'Generate Follow-Up' (stalled / ghosted / needs reply 6+ days)."""
    if na_data is None:
        return False
    return na_data.type in ("follow_up", "ghosted")


def _compute_next_action_for_job(
    job: Job,
    messages: List[Message],
    owner_email: Optional[str],
    now: datetime,
) -> Optional[NextActionData]:
    """Apply priority-ordered rules for a single job."""
    # Terminal stages: no further action suggested.
    try:
        stage = JobStage(job.current_stage)
    except ValueError:
        stage = None

    if stage in (JobStage.REJECTED, JobStage.WITHDRAWN):
        return None

    # Determine last message (if any)
    last_msg: Optional[Message] = None
    if messages:
        last_msg = max(messages, key=_message_timestamp)

    # Rule: Last message is from recruiter (i.e. not the owner)
    if last_msg and owner_email:
        _, from_email = _parse_email_address(last_msg.from_address or "")
        if from_email and from_email != owner_email:
            last_ts = _message_timestamp(last_msg)
            delta_days = (now - last_ts).days

            scheduling_link = _find_scheduling_link(last_msg)

            if delta_days >= NEEDS_REPLY_DAYS:
                label = f"Follow up with recruiter (no reply in {delta_days} days)"
                return NextActionData(
                    type="follow_up",
                    label=label,
                    scheduling_link=scheduling_link,
                )

            return NextActionData(
                type="needs_reply",
                label="You haven't replied yet",
                scheduling_link=scheduling_link,
            )

    # Rule: No activity for GHOSTED_DAYS+ on non-terminal stages
    if job.last_activity:
        last_activity = job.last_activity
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        delta_days = (now - last_activity).days
        if delta_days >= GHOSTED_DAYS:
            return NextActionData(
                type="ghosted",
                label="Ghosted?",
            )

    return None

