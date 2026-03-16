"""Drafts API: create draft reply, get/patch draft, send draft. Human-in-the-loop only."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.draft import MessageDraft, SentMessage
from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.message import Message
from app.models.user import User
from app.providers.gmail import GmailProvider, TokenRefreshError
from app.schemas.draft import (
    DraftReplyRequest,
    DraftReplyResponse,
    DraftReplyResult,
    DraftUpdate,
    MessageDraftSchema,
    ReplyVariantSchema,
)
from app.services.job_processing import _parse_email_address
from app.services.reply_generation import generate_reply_variants

logger = logging.getLogger(__name__)


def _reply_subject_from_original(original_subject: str | None) -> str:
    """Use the same title as the original email; add 'Re: ' if not already present."""
    if not original_subject or not original_subject.strip():
        return "Re: (no subject)"
    s = original_subject.strip()
    if s.upper().startswith("RE:"):
        return s
    return f"Re: {s}"


def create_draft_reply_for_job(
    db: Session,
    auth: AuthContext,
    job_id: uuid.UUID,
    body: DraftReplyRequest,
) -> DraftReplyResponse:
    """Generate 3 reply variants, persist one draft (from first variant), return draft + variants."""
    from fastapi import HTTPException, status

    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    account = _resolve_account_for_job(db, auth.tenant_id, job_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email account available for this job. Connect Gmail for the account that has this thread.",
        )
    user = db.query(User).filter(
        User.id == auth.user_id,
        User.tenant_id == auth.tenant_id,
    ).first()
    user_email = user.email if user else None
    try:
        variants, context_snapshot = generate_reply_variants(
            db=db,
            tenant_id=auth.tenant_id,
            job_id=job_id,
            source_message_id=body.source_message_id,
            user_instruction=body.user_instruction,
            user_email=user_email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    first = variants[0]
    original_subject = None
    if body.source_message_id:
        source_msg = (
            db.query(Message)
            .filter(
                Message.id == body.source_message_id,
                Message.tenant_id == auth.tenant_id,
            )
            .first()
        )
        if source_msg:
            original_subject = source_msg.subject
    if original_subject is None:
        thread_ids = [
            row[0]
            for row in db.query(JobThread.thread_id).filter(
                JobThread.job_id == job_id,
                JobThread.tenant_id == auth.tenant_id,
            ).all()
            if row[0]
        ]
        if thread_ids:
            thread_msg = (
                db.query(Message)
                .filter(
                    Message.tenant_id == auth.tenant_id,
                    Message.thread_id.in_(thread_ids),
                )
                .order_by(Message.date_header.desc().nullslast())
                .first()
            )
            if thread_msg:
                original_subject = thread_msg.subject
    if original_subject is None:
        event_with_msg = (
            db.query(Message)
            .join(JobEvent, JobEvent.message_id == Message.id)
            .filter(
                JobEvent.job_id == job_id,
                JobEvent.tenant_id == auth.tenant_id,
                Message.tenant_id == auth.tenant_id,
            )
            .order_by(Message.date_header.desc().nullslast())
            .first()
        )
        if event_with_msg:
            original_subject = event_with_msg.subject
    reply_subject = _reply_subject_from_original(original_subject) if original_subject is not None else first.subject
    draft = MessageDraft(
        tenant_id=auth.tenant_id,
        job_id=job_id,
        source_message_id=body.source_message_id,
        account_id=account.id,
        draft_type="reply",
        subject=reply_subject,
        body_text=first.body,
        tone=first.tone,
        status="GENERATED",
        generation_context_json=json.dumps(context_snapshot),
        variants_json=json.dumps([v.model_dump() for v in variants]),
        created_by_user_id=auth.user_id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    draft_schema = MessageDraftSchema.model_validate(draft).model_copy(
        update={"variants": variants}
    )
    return DraftReplyResponse(draft=draft_schema, variants=variants)

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _resolve_account_for_job(
    db: Session, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> EmailAccount | None:
    """Resolve email account to use for sending (from job thread or events)."""
    # 1) Via job_threads -> any message in that thread
    thread_rows = (
        db.query(JobThread.thread_id)
        .filter(
            JobThread.job_id == job_id,
            JobThread.tenant_id == tenant_id,
        )
        .all()
    )
    thread_ids = [t[0] for t in thread_rows if t[0]]
    if thread_ids:
        msg = (
            db.query(Message)
            .filter(
                Message.tenant_id == tenant_id,
                Message.thread_id.in_(thread_ids),
            )
            .first()
        )
        if msg and msg.account_id:
            account = db.query(EmailAccount).filter(
                EmailAccount.id == msg.account_id,
                EmailAccount.tenant_id == tenant_id,
            ).first()
            if account:
                return account

    # 2) Via job_events with message_id
    event = (
        db.query(JobEvent)
        .filter(
            JobEvent.job_id == job_id,
            JobEvent.tenant_id == tenant_id,
            JobEvent.message_id.isnot(None),
        )
        .first()
    )
    if event and event.message_id:
        msg = db.query(Message).filter(
            Message.id == event.message_id,
            Message.tenant_id == tenant_id,
        ).first()
        if msg and msg.account_id:
            account = db.query(EmailAccount).filter(
                EmailAccount.id == msg.account_id,
                EmailAccount.tenant_id == tenant_id,
            ).first()
            if account:
                return account

    return None


def _resolve_recipients_and_thread(
    db: Session,
    tenant_id: uuid.UUID,
    draft: MessageDraft,
) -> tuple[list[str], list[str], str | None]:
    """Return (to_addrs, cc_addrs, thread_id). Raises ValueError if no recipients."""
    to_addrs: list[str] = []
    cc_addrs: list[str] = []
    thread_id: str | None = None

    if draft.source_message_id:
        msg = (
            db.query(Message)
            .filter(
                Message.id == draft.source_message_id,
                Message.tenant_id == tenant_id,
            )
            .first()
        )
        if msg:
            thread_id = msg.thread_id
            # Prefer Reply-To header so replies go to the address the sender asked for
            if msg.headers_json:
                try:
                    headers = json.loads(msg.headers_json)
                    reply_to_raw = headers.get("reply-to") if isinstance(headers, dict) else None
                    if reply_to_raw and isinstance(reply_to_raw, str):
                        _, reply_to_email = _parse_email_address(reply_to_raw.strip())
                        if reply_to_email:
                            to_addrs.append(reply_to_email)
                except (json.JSONDecodeError, TypeError):
                    pass
            # Fall back to From, then To
            if not to_addrs and msg.from_address:
                _, from_email = _parse_email_address(msg.from_address.strip())
                if from_email:
                    to_addrs.append(from_email)
            if not to_addrs and msg.to_addresses:
                to_addrs = [a.strip() for a in msg.to_addresses.split(",") if a.strip()]

    # If we still don't have a thread, use the thread of the job's most recent email
    if thread_id is None and draft.job_id:
        thread_ids = [
            row[0]
            for row in db.query(JobThread.thread_id).filter(
                JobThread.job_id == draft.job_id,
                JobThread.tenant_id == tenant_id,
            ).all()
            if row[0]
        ]
        event_msg_ids = [
            row[0]
            for row in db.query(JobEvent.message_id).filter(
                JobEvent.job_id == draft.job_id,
                JobEvent.tenant_id == tenant_id,
                JobEvent.message_id.isnot(None),
            ).all()
            if row[0]
        ]
        if thread_ids or event_msg_ids:
            q = db.query(Message).filter(Message.tenant_id == tenant_id)
            if thread_ids and event_msg_ids:
                from sqlalchemy import or_
                q = q.filter(
                    or_(
                        Message.thread_id.in_(thread_ids),
                        Message.id.in_(event_msg_ids),
                    )
                )
            elif thread_ids:
                q = q.filter(Message.thread_id.in_(thread_ids))
            else:
                q = q.filter(Message.id.in_(event_msg_ids))
            last_msg = q.order_by(Message.date_header.desc().nullslast()).first()
            if last_msg and last_msg.thread_id:
                thread_id = last_msg.thread_id

    if not to_addrs and draft.job_id:
        from app.models.contact import Contact, JobContact
        contacts = (
            db.query(Contact.email)
            .join(JobContact, JobContact.contact_id == Contact.id)
            .filter(
                JobContact.job_id == draft.job_id,
                JobContact.tenant_id == tenant_id,
            )
            .all()
        )
        to_addrs = [c[0] for c in contacts if c[0] and c[0].strip()]

    if not to_addrs:
        raise ValueError("No recipients could be determined for this draft. Add a contact to the job or reply to a message.")

    return to_addrs, cc_addrs, thread_id


def create_draft_from_followup(
    db: Session,
    auth: AuthContext,
    job_id: uuid.UUID,
    result: DraftReplyResult,
) -> MessageDraft:
    """Create a follow_up draft from a generated suggestion. Raises HTTPException on failure."""
    from fastapi import HTTPException, status

    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    account = _resolve_account_for_job(db, auth.tenant_id, job_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email account available for this job. Connect Gmail for the account that has this thread.",
        )
    draft = MessageDraft(
        tenant_id=auth.tenant_id,
        job_id=job_id,
        source_message_id=None,
        account_id=account.id,
        draft_type="follow_up",
        subject=result.subject,
        body_text=result.body,
        tone=result.tone or "professional",
        status="GENERATED",
        generation_context_json=json.dumps({"source": "follow_up_suggestion", "confidence": result.confidence}),
        created_by_user_id=auth.user_id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/{draft_id}", response_model=MessageDraftSchema)
def get_draft(
    draft_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = (
        db.query(MessageDraft)
        .filter(
            MessageDraft.id == draft_id,
            MessageDraft.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )
    schema = MessageDraftSchema.model_validate(draft)
    if draft.variants_json:
        try:
            schema = schema.model_copy(
                update={
                    "variants": [
                        ReplyVariantSchema.model_validate(v)
                        for v in json.loads(draft.variants_json)
                    ]
                }
            )
        except (json.JSONDecodeError, Exception):
            pass
    return schema


@router.patch("/{draft_id}", response_model=MessageDraftSchema)
def update_draft(
    draft_id: uuid.UUID,
    body: DraftUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = (
        db.query(MessageDraft)
        .filter(
            MessageDraft.id == draft_id,
            MessageDraft.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )
    if draft.status == "SENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft already sent",
        )

    updates = body.model_dump(exclude_unset=True)
    if updates:
        if "subject" in updates and updates["subject"] is not None:
            draft.subject = updates["subject"]
        if "body_text" in updates and updates["body_text"] is not None:
            draft.body_text = updates["body_text"]
        if draft.status == "GENERATED":
            draft.status = "EDITED"
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/{draft_id}/send", response_model=MessageDraftSchema)
def send_draft(
    draft_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send the draft via Gmail. Human-in-the-loop: user must have reviewed. Creates sent_messages + REPLY_SENT event."""
    draft = (
        db.query(MessageDraft)
        .filter(
            MessageDraft.id == draft_id,
            MessageDraft.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )
    if draft.status == "SENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft already sent",
        )

    try:
        to_addrs, cc_addrs, thread_id = _resolve_recipients_and_thread(
            db, auth.tenant_id, draft
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.id == draft.account_id,
            EmailAccount.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email account not found",
        )

    provider = GmailProvider(db_session=db)
    try:
        send_result = provider.send_message(
            account=account,
            to_addrs=to_addrs,
            subject=draft.subject or "(no subject)",
            body_text=draft.body_text or "",
            cc_addrs=cc_addrs if cc_addrs else None,
            thread_id=thread_id,
        )
    except ValueError as e:
        draft.status = "FAILED"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except TokenRefreshError as e:
        draft.status = "FAILED"
        db.commit()
        logger.warning("Gmail send failed (token): draft_id=%s %s", draft_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gmail authentication failed. Reconnect the account in Settings.",
        )
    except Exception as e:
        draft.status = "FAILED"
        db.commit()
        logger.exception("Gmail send failed draft_id=%s", draft_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Send failed: {str(e)[:200]}",
        )

    sent = SentMessage(
        tenant_id=auth.tenant_id,
        job_id=draft.job_id,
        account_id=draft.account_id,
        provider="gmail",
        provider_message_id=send_result.provider_message_id,
        thread_id=send_result.thread_id or thread_id,
        to_addrs_json=json.dumps(to_addrs),
        cc_addrs_json=json.dumps(cc_addrs) if cc_addrs else None,
        subject=draft.subject,
        body_text=draft.body_text,
    )
    db.add(sent)

    draft.status = "SENT"
    db.add(
        JobEvent(
            tenant_id=auth.tenant_id,
            job_id=draft.job_id,
            event_type="REPLY_SENT",
            source="send",
            rationale=f"Reply sent via app (draft_id={draft_id})",
        )
    )
    db.commit()
    db.refresh(draft)
    return draft
