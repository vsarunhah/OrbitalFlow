"""Job resolution and event processing.

Flow (called after LLM extraction):
  1. Resolve extraction -> existing Job  (thread > req_id > fuzzy company+role)
  2. If no match, create a new Job
  3. Link thread_id to the job
  4. Create a JobEvent row
  5. Run the deterministic stage reducer
  6. If stage changed, update Job.current_stage and write JobStageHistory
  7. Always update Job.last_activity
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parseaddr as _parseaddr

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.contact import Contact, ContactAffiliation, JobContact
from app.models.job import (
    Job,
    JobEvent,
    JobIdentity,
    JobStageHistory,
    JobThread,
)
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.schemas.job import JobStage
from app.services.stage_reducer import compute_new_stage

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.75
# Identities must resemble the job's primary company (guards stale aliases after renames
# and platform names like "Paraform" stored on employer jobs).
IDENTITY_ALIAS_THRESHOLD = 0.85
# Recruiting marketplaces — not the hiring company when the subject says "referred on …".
RECRUITING_PLATFORMS = frozenset({"paraform"})


def _dt_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def message_activity_at(message: Message) -> datetime:
    """Prefer the email Date header, then the message row timestamp."""
    if message.date_header:
        return _dt_utc(message.date_header)
    if message.created_at:
        return _dt_utc(message.created_at)
    return datetime.now(timezone.utc)


def bump_job_last_activity_if_newer(job: Job, at: datetime) -> None:
    """Keep Job.last_activity as the latest known thread activity (updates Job.updated_at)."""
    at = _dt_utc(at)
    if job.last_activity is None:
        job.last_activity = at
        return
    if at > _dt_utc(job.last_activity):
        job.last_activity = at


def process_extraction_for_job(
    db: Session,
    message: Message,
    extraction: MessageExtraction,
) -> Job | None:
    """Main entry point: resolve or create a job, apply event + reducer."""
    if extraction.status != "completed":
        return None
    if extraction.event_type == "JOB_ALERT":
        return None
    if extraction.event_type in (None, "NONE", "FOLLOW_UP"):
        if extraction.category != "RECRUITER":
            return None

    tenant_id = extraction.tenant_id

    job = _resolve_job(db, tenant_id, message, extraction)
    created = False

    if job is None:
        job = _create_job(db, tenant_id, extraction, message)
        created = True

    _ensure_thread_link(db, tenant_id, job, message)
    if created and extraction.company and extraction.role:
        if _should_store_identity(job, extraction.company):
            _add_identity(db, tenant_id, job, extraction)

    _create_contacts_for_job(db, tenant_id, job, message, extraction)

    stage_before = job.current_stage
    new_stage = compute_new_stage(
        current_stage=JobStage(stage_before),
        event_type=extraction.event_type,
        confidence=extraction.confidence or 0.0,
    )
    stage_after = new_stage.value if new_stage else stage_before

    event = JobEvent(
        tenant_id=tenant_id,
        job_id=job.id,
        message_id=message.id,
        extraction_id=extraction.id,
        event_type=extraction.event_type,
        confidence=extraction.confidence,
        rationale=extraction.rationale,
        stage_before=stage_before,
        stage_after=stage_after,
        source="extraction",
    )
    db.add(event)

    if new_stage is not None:
        job.current_stage = new_stage.value
        job.confidence = extraction.confidence

        history = JobStageHistory(
            tenant_id=tenant_id,
            job_id=job.id,
            message_id=message.id,
            stage_before=stage_before,
            stage_after=new_stage.value,
            source="auto",
            rationale=extraction.rationale,
        )
        db.add(history)

    bump_job_last_activity_if_newer(job, message_activity_at(message))
    db.commit()

    logger.info(
        "Job processed job_id=%s stage=%s->%s event=%s (created=%s)",
        job.id,
        stage_before,
        stage_after,
        extraction.event_type,
        created,
    )
    return job


# --------------- resolution helpers ---------------


def _resolve_job(
    db: Session,
    tenant_id: uuid.UUID,
    message: Message,
    extraction: MessageExtraction,
) -> Job | None:
    # 1) Thread match (strongest signal)
    if message.thread_id:
        jt = (
            db.query(JobThread)
            .filter(
                JobThread.tenant_id == tenant_id,
                JobThread.thread_id == message.thread_id,
            )
            .first()
        )
        if jt:
            return db.query(Job).filter(Job.id == jt.job_id).first()

    # 2) req_id match
    if extraction.req_id:
        job = (
            db.query(Job)
            .filter(Job.tenant_id == tenant_id, Job.req_id == extraction.req_id)
            .first()
        )
        if job:
            return job

    # 3) Fuzzy company + role fallback
    if extraction.company and extraction.role:
        return _fuzzy_match(db, tenant_id, extraction.company, extraction.role)

    return None


def _fuzzy_match(
    db: Session,
    tenant_id: uuid.UUID,
    company: str,
    role: str,
) -> Job | None:
    """Simple SequenceMatcher-based fuzzy match against existing jobs + identities."""
    candidates = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.company.isnot(None),
            Job.role.isnot(None),
        )
        .all()
    )

    best_job: Job | None = None
    best_score = 0.0

    for cand in candidates:
        score = _similarity(company, cand.company) * 0.6 + _similarity(role, cand.role) * 0.4
        if score > best_score:
            best_score = score
            best_job = cand

    identities = (
        db.query(JobIdentity)
        .filter(
            JobIdentity.tenant_id == tenant_id,
            JobIdentity.company.isnot(None),
            JobIdentity.role.isnot(None),
        )
        .all()
    )
    for ident in identities:
        ident_job = db.query(Job).filter(Job.id == ident.job_id).first()
        if not ident_job or not _identity_belongs_to_job(ident_job, ident):
            continue
        score = _similarity(company, ident.company) * 0.6 + _similarity(role, ident.role) * 0.4
        if score > best_score:
            best_score = score
            best_job = ident_job

    if best_score >= FUZZY_THRESHOLD:
        return best_job
    return None


def _similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_company(name: str | None) -> str:
    if not name:
        return ""
    return name.lower().strip()


def _is_recruiting_platform(company: str | None) -> bool:
    return _normalize_company(company) in RECRUITING_PLATFORMS


def _identity_belongs_to_job(job: Job, identity: JobIdentity) -> bool:
    """True when an identity row is a plausible alias for the job's employer."""
    if not identity.company or not job.company:
        return False
    if _is_recruiting_platform(identity.company) and not _is_recruiting_platform(job.company):
        return False
    return _similarity(identity.company, job.company) >= IDENTITY_ALIAS_THRESHOLD


def _should_store_identity(job: Job, company: str) -> bool:
    """Skip platform/marketplace names as aliases on unrelated employer jobs."""
    if not job.company:
        return True
    if _is_recruiting_platform(company) and not _is_recruiting_platform(job.company):
        return False
    return _similarity(company, job.company) >= IDENTITY_ALIAS_THRESHOLD


# --------------- creation helpers ---------------


def _create_job(
    db: Session,
    tenant_id: uuid.UUID,
    extraction: MessageExtraction,
    message: Message,
) -> Job:
    job = Job(
        tenant_id=tenant_id,
        company=extraction.company,
        role=extraction.role,
        req_id=extraction.req_id,
        current_stage=JobStage.SOURCED.value,
        last_activity=message_activity_at(message),
    )
    db.add(job)
    db.flush()
    return job


def _ensure_thread_link(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    message: Message,
) -> None:
    if not message.thread_id:
        return
    existing = (
        db.query(JobThread)
        .filter(
            JobThread.tenant_id == tenant_id,
            JobThread.thread_id == message.thread_id,
        )
        .first()
    )
    if existing:
        return
    db.add(JobThread(tenant_id=tenant_id, job_id=job.id, thread_id=message.thread_id))
    db.flush()


def _add_identity(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    extraction: MessageExtraction,
) -> None:
    db.add(
        JobIdentity(
            tenant_id=tenant_id,
            job_id=job.id,
            company=extraction.company,
            role=extraction.role,
            req_id=extraction.req_id,
        )
    )
    db.flush()


# --------------- contact helpers ---------------


def _parse_email_address(raw: str) -> tuple[str | None, str]:
    """Extract (display_name, email) from an RFC 2822 address string.

    "Sabrina Baez <sabrina@doss.com>" -> ("Sabrina Baez", "sabrina@doss.com")
    "sabrina@doss.com"                -> (None,           "sabrina@doss.com")
    """
    display, addr = _parseaddr(raw)
    return (display.strip() or None, addr.strip().lower())


def _create_contacts_for_job(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    message: Message,
    extraction: MessageExtraction,
) -> None:
    """Upsert Contact + ContactAffiliation + JobContact from extraction contacts.

    Falls back to message.from_address when a contact has no email (common
    for recruiter outreach where the sender IS the recruiter).
    Skips contacts whose email matches the user's own account email.
    """
    raw = extraction.contacts_json
    if not raw:
        return

    try:
        contacts_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Invalid contacts_json for extraction_id=%s", extraction.id
        )
        return

    if not isinstance(contacts_data, list):
        return

    from app.models.email_account import EmailAccount

    account = (
        db.query(EmailAccount)
        .filter(EmailAccount.id == message.account_id)
        .first()
    )
    owner_email = account.email_address.strip().lower() if account else None

    from_display_name, from_email = _parse_email_address(
        message.from_address or ""
    )

    # Track (job_id, contact_id) we've already linked this batch to avoid
    # duplicate JobContact when the same contact appears twice with different roles.
    seen_job_contact: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for entry in contacts_data:
        raw_email = (entry.get("email") or "").strip()
        _, email = _parse_email_address(raw_email) if raw_email else (None, "")

        name = entry.get("name")

        if not email and from_email:
            email = from_email
            if not name:
                name = from_display_name

        if not email:
            continue
        if email == owner_email:
            continue

        contact_role = entry.get("role") or "recruiter"

        contact = _upsert_contact(db, tenant_id, email, name)
        if contact is None:
            continue

        if extraction.company:
            aff_type = _infer_affiliation_type(
                extraction.company,
                extraction.role,
                extraction.category,
            )
            _upsert_affiliation(
                db,
                tenant_id,
                contact,
                extraction.company,
                contact_role,
                affiliation_type=aff_type,
            )

        key = (job.id, contact.id)
        if key not in seen_job_contact:
            seen_job_contact.add(key)
            _upsert_job_contact(db, tenant_id, job, contact, contact_role)

    db.flush()


def _upsert_contact(
    db: Session,
    tenant_id: uuid.UUID,
    email: str,
    name: str | None,
) -> Contact | None:
    """Get-or-create a Contact by (tenant_id, email).

    Also self-heals contacts that were stored with full RFC-format emails
    (e.g. "name <addr>") by normalising them to bare addresses.
    """
    contact = (
        db.query(Contact)
        .filter(Contact.tenant_id == tenant_id, Contact.email == email)
        .first()
    )

    if not contact:
        rfc_pattern = f"<{email}>"
        contact = (
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.email.contains(rfc_pattern),
            )
            .first()
        )
        if contact:
            contact.email = email

    if contact:
        if name:
            contact.name = name
        return contact

    contact = Contact(tenant_id=tenant_id, email=email, name=name)
    db.add(contact)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return (
            db.query(Contact)
            .filter(Contact.tenant_id == tenant_id, Contact.email == email)
            .first()
        )
    return contact


def _infer_affiliation_type(
    company: str | None,
    title: str | None,
    category: str | None,
) -> str | None:
    """Infer agency vs company for RECRUITER-category extractions."""
    if category != "RECRUITER":
        return None
    combined = f" {(company or '').lower()} {(title or '').lower()} "
    agency_keywords = ("recruiting", "staffing", "talent", "recruitment")
    if any(kw in combined for kw in agency_keywords):
        return "agency"
    return "company"


def _upsert_affiliation(
    db: Session,
    tenant_id: uuid.UUID,
    contact: Contact,
    company: str,
    title: str | None,
    affiliation_type: str | None = None,
) -> None:
    """Add a ContactAffiliation if one doesn't already exist for this company."""
    existing = (
        db.query(ContactAffiliation)
        .filter(
            ContactAffiliation.contact_id == contact.id,
            ContactAffiliation.tenant_id == tenant_id,
            ContactAffiliation.company == company,
        )
        .first()
    )
    if existing:
        return
    db.add(
        ContactAffiliation(
            tenant_id=tenant_id,
            contact_id=contact.id,
            company=company,
            title=title,
            affiliation_type=affiliation_type,
        )
    )


def _upsert_job_contact(
    db: Session,
    tenant_id: uuid.UUID,
    job: Job,
    contact: Contact,
    role: str,
) -> None:
    """Link a contact to a job if not already linked."""
    existing = (
        db.query(JobContact)
        .filter(
            JobContact.tenant_id == tenant_id,
            JobContact.job_id == job.id,
            JobContact.contact_id == contact.id,
        )
        .first()
    )
    if existing:
        return
    db.add(
        JobContact(
            tenant_id=tenant_id,
            job_id=job.id,
            contact_id=contact.id,
            role=role,
        )
    )
