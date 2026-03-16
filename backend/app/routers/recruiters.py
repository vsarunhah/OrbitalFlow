"""Recruiters view: contacts with affiliations and associated jobs."""

from __future__ import annotations

import uuid
from collections import defaultdict
from email.utils import parseaddr
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sa_func, or_
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.contact import Contact, ContactAffiliation, JobContact
from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.schemas.recruiter import (
    AffiliationOut,
    RecruiterDetail,
    RecruiterJobOut,
    RecruiterListResponse,
    RecruiterSummary,
    RecruitersMergeRequest,
    RecruitersMergeResult,
)

router = APIRouter(prefix="/recruiters", tags=["recruiters"])


def _normalize_from_email(raw: str | None) -> str:
    """Extract lowercase email from RFC 2822 address string."""
    if not raw:
        return ""
    _, addr = parseaddr(raw)
    return addr.strip().lower()


def _get_processed_message_sender_counts(
    db: Session, tenant_id: uuid.UUID
) -> dict[str, int]:
    """Count processed messages by normalized sender email (MessageExtraction + JobEvent)."""
    msg_ids = set()
    for row in (
        db.query(MessageExtraction.message_id)
        .filter(MessageExtraction.tenant_id == tenant_id)
        .distinct()
        .all()
    ):
        msg_ids.add(row[0])
    for row in (
        db.query(JobEvent.message_id)
        .filter(
            JobEvent.tenant_id == tenant_id,
            JobEvent.message_id.isnot(None),
        )
        .distinct()
        .all()
    ):
        msg_ids.add(row[0])
    if not msg_ids:
        return {}
    messages = (
        db.query(Message.id, Message.from_address)
        .filter(Message.id.in_(msg_ids))
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for _mid, from_addr in messages:
        email = _normalize_from_email(from_addr)
        if email:
            counts[email] += 1
    return dict(counts)


def _company_set_and_primary_agency(
    contact: Contact,
    job_by_id: dict[uuid.UUID, Job] | None = None,
) -> tuple[set[str], str | None]:
    """Distinct companies from affiliations + jobs (via job_contacts); first agency company."""
    job_by_id = job_by_id or {}
    companies: set[str] = set()
    primary_agency: str | None = None
    for a in contact.affiliations:
        if a.company:
            companies.add(a.company)
            if primary_agency is None and a.affiliation_type == "agency":
                primary_agency = a.company
    for jc in contact.job_contacts:
        job = job_by_id.get(jc.job_id)
        if job and job.company:
            companies.add(job.company)
    return companies, primary_agency


def _merge_contact_into_target(
    db: Session,
    tenant_id: uuid.UUID,
    source: Contact,
    target: Contact,
) -> None:
    """Merge source contact into target: move job_contacts, copy affiliations, delete source."""
    if source.id == target.id:
        return

    # Move job_contacts: point to target; avoid duplicate (tenant_id, job_id, contact_id)
    target_job_ids = {
        jc.job_id
        for jc in db.query(JobContact).filter(
            JobContact.contact_id == target.id,
            JobContact.tenant_id == tenant_id,
        ).all()
    }
    source_jcs = (
        db.query(JobContact)
        .filter(
            JobContact.contact_id == source.id,
            JobContact.tenant_id == tenant_id,
        )
        .all()
    )
    for jc in source_jcs:
        if jc.job_id in target_job_ids:
            db.delete(jc)
        else:
            jc.contact_id = target.id
            target_job_ids.add(jc.job_id)

    # Copy affiliations from source to target (skip if target already has same company+title)
    existing_pairs = {
        (a.company or "", a.title or "")
        for a in db.query(ContactAffiliation).filter(
            ContactAffiliation.contact_id == target.id,
        ).all()
    }
    for aff in source.affiliations:
        key = (aff.company or "", aff.title or "")
        if key not in existing_pairs:
            db.add(
                ContactAffiliation(
                    tenant_id=tenant_id,
                    contact_id=target.id,
                    company=aff.company,
                    title=aff.title,
                    affiliation_type=aff.affiliation_type,
                )
            )
            existing_pairs.add(key)

    db.delete(source)


@router.post("/merge", response_model=RecruitersMergeResult)
def merge_recruiters(
    body: RecruitersMergeRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually merge multiple recruiters (contacts) into one. Target is kept; sources are removed."""
    if body.target_contact_id in body.source_contact_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_contact_id must not be in source_contact_ids",
        )

    all_ids = [body.target_contact_id] + list(body.source_contact_ids)
    contacts = (
        db.query(Contact)
        .filter(Contact.id.in_(all_ids), Contact.tenant_id == auth.tenant_id)
        .all()
    )
    by_id = {c.id: c for c in contacts}
    target = by_id.get(body.target_contact_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target recruiter not found",
        )

    missing = [sid for sid in body.source_contact_ids if sid not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source recruiter(s) not found: {missing}",
        )

    for sid in body.source_contact_ids:
        _merge_contact_into_target(db, auth.tenant_id, by_id[sid], target)

    db.commit()
    db.refresh(target)

    return RecruitersMergeResult(
        merged_contact_id=target.id,
        removed_contact_ids=list(body.source_contact_ids),
        status="merged",
    )


@router.get("", response_model=RecruiterListResponse)
def list_recruiters(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    query: Optional[str] = Query(None, description="Search by name or email"),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner_emails = {
        row.email_address.strip().lower()
        for row in db.query(EmailAccount.email_address)
        .filter(EmailAccount.tenant_id == auth.tenant_id)
        .all()
    }

    recruiter_ids_q = (
        db.query(JobContact.contact_id)
        .filter(JobContact.tenant_id == auth.tenant_id)
        .distinct()
        .subquery()
    )

    base_q = db.query(Contact).filter(
        Contact.tenant_id == auth.tenant_id,
        Contact.id.in_(db.query(recruiter_ids_q.c.contact_id)),
    )

    if owner_emails:
        exclude = []
        for oe in owner_emails:
            exclude.append(Contact.email == oe)
            exclude.append(Contact.email.contains(f"<{oe}>"))
        base_q = base_q.filter(~or_(*exclude))

    if query and query.strip():
        pattern = f"%{query.strip()}%"
        base_q = base_q.filter(
            or_(
                Contact.email.ilike(pattern),
                (Contact.name.isnot(None)) & Contact.name.ilike(pattern),
            )
        )

    total = base_q.count()

    contacts = (
        base_q
        .options(
            joinedload(Contact.affiliations),
            joinedload(Contact.job_contacts),
        )
        .order_by(Contact.updated_at.desc(), Contact.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    sender_counts = _get_processed_message_sender_counts(db, auth.tenant_id)
    job_ids = {
        jc.job_id
        for c in contacts
        for jc in c.job_contacts
    }
    job_by_id = (
        {j.id: j for j in db.query(Job).filter(Job.id.in_(job_ids)).all()}
        if job_ids
        else {}
    )

    items = []
    for c in contacts:
        job_count = len(
            [jc for jc in c.job_contacts if jc.tenant_id == auth.tenant_id]
        )
        companies_set, primary_agency = _company_set_and_primary_agency(
            c, job_by_id
        )
        items.append(
            RecruiterSummary(
                id=c.id,
                name=c.name,
                email=c.email,
                affiliations=[
                    AffiliationOut.model_validate(a) for a in c.affiliations
                ],
                job_count=job_count,
                message_count=sender_counts.get(c.email, 0),
                company_count=len(companies_set),
                primary_agency=primary_agency,
            )
        )

    return RecruiterListResponse(items=items, total=total)


@router.delete("/{recruiter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recruiter(
    recruiter_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(Contact)
        .filter(Contact.id == recruiter_id, Contact.tenant_id == auth.tenant_id)
        .first()
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recruiter not found"
        )

    db.delete(contact)
    db.commit()
    return None


@router.get("/{recruiter_id}", response_model=RecruiterDetail)
def get_recruiter(
    recruiter_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(Contact)
        .filter(Contact.id == recruiter_id, Contact.tenant_id == auth.tenant_id)
        .first()
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recruiter not found"
        )

    jc_rows = (
        db.query(JobContact, Job)
        .join(Job, Job.id == JobContact.job_id)
        .filter(
            JobContact.contact_id == contact.id,
            JobContact.tenant_id == auth.tenant_id,
        )
        .all()
    )

    jobs = [
        RecruiterJobOut(
            job_id=job.id,
            company=job.company,
            role=job.role,
            current_stage=job.current_stage,
            contact_role=jc.role,
        )
        for jc, job in jc_rows
    ]

    job_by_id = {job.id: job for _jc, job in jc_rows}
    companies_set, primary_agency = _company_set_and_primary_agency(
        contact, job_by_id
    )
    sender_counts = _get_processed_message_sender_counts(db, auth.tenant_id)

    return RecruiterDetail(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        affiliations=[
            AffiliationOut.model_validate(a) for a in contact.affiliations
        ],
        jobs=jobs,
        created_at=contact.created_at,
        message_count=sender_counts.get(contact.email, 0),
        company_count=len(companies_set),
        primary_agency=primary_agency,
        companies=sorted(companies_set),
    )
