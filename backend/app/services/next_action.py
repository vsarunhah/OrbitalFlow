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

from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.models.job import Job
from app.models.message import Message
from app.schemas.job import JobStage
from app.services.job_messages import load_accounts_for_messages, load_messages_for_jobs
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
    messages_by_job: Optional[Dict[uuid.UUID, List[Message]]] = None,
    needs_reply_dismissed_message_by_job: Optional[
        Dict[uuid.UUID, Optional[uuid.UUID]]
    ] = None,
) -> Dict[uuid.UUID, Optional[NextActionData]]:
    """Return a mapping of job_id -> NextActionData | None."""
    job_list = list(jobs)
    if not job_list:
        return {}

    if messages_by_job is None:
        messages_by_job = load_messages_for_jobs(db, tenant_id, job_list)

    accounts_by_id: Dict[uuid.UUID, EmailAccount] = load_accounts_for_messages(
        db, messages_by_job
    )

    dismiss_map = needs_reply_dismissed_message_by_job or {}

    # 6) Compute next action per job
    result: Dict[uuid.UUID, Optional[NextActionData]] = {}
    now = datetime.now(timezone.utc)

    for job in job_list:
        msgs = messages_by_job.get(job.id, [])
        owner_email = infer_owner_email(msgs, accounts_by_id)
        dismissed = dismiss_map.get(job.id)
        action = _compute_next_action_for_job(
            job, msgs, owner_email, now, needs_reply_dismissed_message_id=dismissed
        )
        result[job.id] = action

    return result


def infer_owner_email(
    messages: List[Message],
    accounts_by_id: Dict[uuid.UUID, EmailAccount],
) -> Optional[str]:
    """Best-effort guess of the user's own email address for a job."""
    for msg in messages:
        account = accounts_by_id.get(msg.account_id)
        if account and account.email_address:
            return account.email_address.strip().lower()
    return None


def message_timestamp(msg: Message) -> datetime:
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


def needs_reply_dismissal_target_message_id(
    job: Job,
    messages: List[Message],
    owner_email: Optional[str],
) -> Optional[uuid.UUID]:
    """If the last thread message is inbound from a non-owner, return its id; else None."""
    try:
        stage = JobStage(job.current_stage)
    except ValueError:
        return None
    if stage in (JobStage.REJECTED, JobStage.WITHDRAWN):
        return None
    if not messages or not owner_email:
        return None
    last_msg = max(messages, key=message_timestamp)
    _, from_email = _parse_email_address(last_msg.from_address or "")
    if from_email and from_email != owner_email:
        return last_msg.id
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
    needs_reply_dismissed_message_id: Optional[uuid.UUID] = None,
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
        last_msg = max(messages, key=message_timestamp)

    # Rule: Last message is from recruiter (i.e. not the owner)
    if last_msg and owner_email:
        _, from_email = _parse_email_address(last_msg.from_address or "")
        if from_email and from_email != owner_email:
            if not (
                needs_reply_dismissed_message_id
                and needs_reply_dismissed_message_id == last_msg.id
            ):
                last_ts = message_timestamp(last_msg)
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

