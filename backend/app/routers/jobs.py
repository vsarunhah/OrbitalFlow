"""Jobs API: list with search/filter/sort, detail, timeline, manual stage override."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.job import (
    Job,
    JobEvent,
    JobIdentity,
    JobManualChange,
    JobStageHistory,
    JobThread,
)
from app.models.message import Message
from app.models.draft import MessageDraft, SentMessage
from app.schemas.job import (
    JobDetail,
    JobListResponse,
    JobStage,
    JobSummary,
    JobsMergeRequest,
    JobsMergeResult,
    JobTimeline,
    JobUpdate,
    ManualStageChange,
    NextAction,
    TimelineEvent,
    TimelineMessage,
    TimelineSentMessage,
)
from app.schemas.draft import (
    DraftReplyRequest,
    DraftReplyResponse,
    FollowUpSuggestionResponse,
    MessageDraftSchema,
    ReplyVariantSchema,
)
from app.services.followup_generation import generate_followup_suggestion
from app.services.job_merge import merge_job_into_target
from app.services.next_action import (
    compute_next_actions_for_jobs,
    suggest_followup_for_next_action,
)
from app.routers import drafts as drafts_router

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/merge", response_model=JobsMergeResult)
def merge_jobs(
    body: JobsMergeRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually merge multiple jobs into one. Target job is kept; source jobs are removed."""
    all_ids = [body.target_job_id] + list(body.source_job_ids)
    if body.target_job_id in body.source_job_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_job_id must not be in source_job_ids",
        )

    jobs = (
        db.query(Job)
        .filter(Job.id.in_(all_ids), Job.tenant_id == auth.tenant_id)
        .all()
    )
    by_id = {j.id: j for j in jobs}
    target = by_id.get(body.target_job_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target job not found",
        )

    missing = [sid for sid in body.source_job_ids if sid not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source job(s) not found: {missing}",
        )

    for sid in body.source_job_ids:
        merge_job_into_target(db, by_id[sid], target)

    db.commit()
    db.refresh(target)

    return JobsMergeResult(
        merged_job_id=target.id,
        removed_job_ids=list(body.source_job_ids),
        status="merged",
    )


@router.get("", response_model=JobListResponse)
def list_jobs(
    query: Optional[str] = Query(None, description="Full-text search over message bodies"),
    stage: Optional[str] = Query(None, description="Filter by current_stage (e.g. APPLIED,INTERVIEW)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_q = db.query(Job).filter(Job.tenant_id == auth.tenant_id)

    if stage:
        stages = [s.strip().upper() for s in stage.split(",") if s.strip()]
        if stages:
            base_q = base_q.filter(Job.current_stage.in_(stages))

    if query and query.strip():
        ts_query = sa_func.plainto_tsquery("english", query.strip())
        matching_msg_ids = (
            db.query(Message.id)
            .filter(
                Message.tenant_id == auth.tenant_id,
                Message.body_text_tsv.op("@@")(ts_query),
            )
            .subquery()
        )
        # Messages link to jobs via job_events
        matching_job_ids_via_events = (
            db.query(JobEvent.job_id)
            .filter(JobEvent.message_id.in_(db.query(matching_msg_ids.c.id)))
            .distinct()
            .subquery()
        )
        # Also check via job_threads -> messages.thread_id
        matching_thread_ids = (
            db.query(Message.thread_id)
            .filter(
                Message.id.in_(db.query(matching_msg_ids.c.id)),
                Message.thread_id.isnot(None),
            )
            .distinct()
            .subquery()
        )
        matching_job_ids_via_threads = (
            db.query(JobThread.job_id)
            .filter(
                JobThread.tenant_id == auth.tenant_id,
                JobThread.thread_id.in_(db.query(matching_thread_ids.c.thread_id)),
            )
            .distinct()
            .subquery()
        )

        # Also search company/role directly
        like_pattern = f"%{query.strip()}%"
        base_q = base_q.filter(
            Job.id.in_(db.query(matching_job_ids_via_events.c.job_id))
            | Job.id.in_(db.query(matching_job_ids_via_threads.c.job_id))
            | Job.company.ilike(like_pattern)
            | Job.role.ilike(like_pattern)
        )

    total = base_q.count()

    rows: list[Job] = (
        base_q
        .order_by(Job.last_activity.desc().nullslast(), Job.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    next_actions_by_job = compute_next_actions_for_jobs(
        db=db,
        tenant_id=auth.tenant_id,
        jobs=rows,
    )

    summaries: list[JobSummary] = []
    for row in rows:
        summary = JobSummary.model_validate(row)
        na_data = next_actions_by_job.get(row.id)
        summary.next_action = (
            NextAction(
                type=na_data.type,
                label=na_data.label,
                due_at=na_data.due_at,
                scheduling_link=na_data.scheduling_link,
            )
            if na_data
            else None
        )
        summary.suggest_followup = suggest_followup_for_next_action(na_data)
        summaries.append(summary)

    return JobListResponse(
        items=summaries,
        total=total,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Clean up all dependent rows that reference this job to satisfy FK constraints.
    db.query(MessageDraft).filter(MessageDraft.job_id == job_id).delete()
    db.query(SentMessage).filter(SentMessage.job_id == job_id).delete()
    db.query(JobEvent).filter(JobEvent.job_id == job_id).delete()
    db.query(JobThread).filter(JobThread.job_id == job_id).delete()
    db.query(JobStageHistory).filter(JobStageHistory.job_id == job_id).delete()
    db.query(JobManualChange).filter(JobManualChange.job_id == job_id).delete()
    db.query(JobIdentity).filter(JobIdentity.job_id == job_id).delete()

    db.delete(job)
    db.commit()
    return None


@router.post("/{job_id}/draft-reply", response_model=DraftReplyResponse)
def create_draft_reply(
    job_id: uuid.UUID,
    body: DraftReplyRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate 3 reply variants and store one draft (first variant). Returns draft + variants."""
    return drafts_router.create_draft_reply_for_job(db, auth, job_id, body)


@router.post("/{job_id}/follow-up-suggestion", response_model=FollowUpSuggestionResponse)
def create_followup_suggestion(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a follow-up email suggestion for a stalled job and create a draft. Show 'Generate Follow-Up' when job.suggest_followup is true."""
    from app.models.user import User

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
    na_map = compute_next_actions_for_jobs(db=db, tenant_id=auth.tenant_id, jobs=[job])
    na_data = na_map.get(job.id)
    if not suggest_followup_for_next_action(na_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This job is not in a stalled state. Follow-up suggestion is offered when the recruiter hasn't been replied to for a while or the thread is ghosted.",
        )
    user = (
        db.query(User)
        .filter(User.id == auth.user_id, User.tenant_id == auth.tenant_id)
        .first()
    )
    user_email = user.email if user else None
    try:
        result = generate_followup_suggestion(
            db=db,
            tenant_id=auth.tenant_id,
            job_id=job_id,
            user_email=user_email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    draft = drafts_router.create_draft_from_followup(db, auth, job_id, result)
    draft_schema = MessageDraftSchema.model_validate(draft)
    return FollowUpSuggestionResponse(
        subject=result.subject,
        body=result.body,
        tone=result.tone,
        confidence=result.confidence,
        draft=draft_schema,
    )


@router.get("/{job_id}", response_model=JobDetail)
def get_job(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    na_map = compute_next_actions_for_jobs(
        db=db,
        tenant_id=auth.tenant_id,
        jobs=[job],
    )
    na_data = na_map.get(job.id)

    detail = JobDetail.model_validate(job)
    detail.next_action = (
        NextAction(
            type=na_data.type,
            label=na_data.label,
            due_at=na_data.due_at,
            scheduling_link=na_data.scheduling_link,
        )
        if na_data
        else None
    )
    detail.suggest_followup = suggest_followup_for_next_action(na_data)
    return detail


@router.get("/{job_id}/draft", response_model=MessageDraftSchema)
def get_job_draft(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the most recent unsent draft for this job, if any. 404 if none."""
    draft = (
        db.query(MessageDraft)
        .filter(
            MessageDraft.job_id == job_id,
            MessageDraft.tenant_id == auth.tenant_id,
            MessageDraft.status != "SENT",
        )
        .order_by(MessageDraft.created_at.desc())
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No unsent draft for this job",
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


@router.patch("/{job_id}", response_model=JobDetail)
def update_job(
    job_id: uuid.UUID,
    body: JobUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field, value in updates.items():
        setattr(job, field, value)

    job.last_activity = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}/timeline", response_model=JobTimeline)
def get_timeline(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    events = (
        db.query(JobEvent)
        .filter(JobEvent.job_id == job_id)
        .order_by(JobEvent.created_at.asc())
        .all()
    )

    # Gather messages: via job_events.message_id and via job_threads
    event_msg_ids = {e.message_id for e in events if e.message_id}

    thread_ids = (
        db.query(JobThread.thread_id)
        .filter(JobThread.job_id == job_id)
        .all()
    )
    thread_id_list = [t[0] for t in thread_ids]

    messages_q = db.query(Message).filter(Message.tenant_id == auth.tenant_id)
    if event_msg_ids and thread_id_list:
        messages_q = messages_q.filter(
            Message.id.in_(event_msg_ids) | Message.thread_id.in_(thread_id_list)
        )
    elif event_msg_ids:
        messages_q = messages_q.filter(Message.id.in_(event_msg_ids))
    elif thread_id_list:
        messages_q = messages_q.filter(Message.thread_id.in_(thread_id_list))
    else:
        messages_q = messages_q.filter(False)

    msgs = messages_q.order_by(Message.date_header.asc().nullslast()).all()

    def to_timeline_message(m: Message) -> TimelineMessage:
        from app.llm.prompts import strip_quoted_replies

        raw = (m.body_text or "").strip()
        cleaned = strip_quoted_replies(raw) if raw else ""
        snippet = cleaned[:300] if cleaned else None
        return TimelineMessage(
            id=m.id,
            subject=m.subject,
            from_address=m.from_address,
            date_header=m.date_header,
            body_snippet=snippet,
            provider_msg_id=m.provider_msg_id,
        )

    na_map = compute_next_actions_for_jobs(
        db=db,
        tenant_id=auth.tenant_id,
        jobs=[job],
    )
    na_data = na_map.get(job.id)

    job_detail = JobDetail.model_validate(job)
    job_detail.next_action = (
        NextAction(
            type=na_data.type,
            label=na_data.label,
            due_at=na_data.due_at,
            scheduling_link=na_data.scheduling_link,
        )
        if na_data
        else None
    )
    job_detail.suggest_followup = suggest_followup_for_next_action(na_data)

    sent_list = (
        db.query(SentMessage)
        .filter(
            SentMessage.job_id == job_id,
            SentMessage.tenant_id == auth.tenant_id,
        )
        .order_by(SentMessage.sent_at.asc())
        .all()
    )

    def to_timeline_sent(s: SentMessage) -> TimelineSentMessage:
        body = (s.body_text or "").strip()
        snippet = body[:300] if body else None
        return TimelineSentMessage(
            id=s.id,
            subject=s.subject,
            to_addrs_json=s.to_addrs_json,
            body_snippet=snippet,
            provider_message_id=s.provider_message_id,
            sent_at=s.sent_at,
        )

    return JobTimeline(
        job=job_detail,
        events=[TimelineEvent.model_validate(e) for e in events],
        messages=[to_timeline_message(m) for m in msgs],
        sent_messages=[to_timeline_sent(s) for s in sent_list],
    )


@router.post("/{job_id}/stage", response_model=JobDetail)
def manual_stage_override(
    job_id: uuid.UUID,
    body: ManualStageChange,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == auth.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    stage_before = job.current_stage

    if stage_before == body.new_stage.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is already in that stage",
        )

    job.current_stage = body.new_stage.value
    job.last_activity = datetime.now(timezone.utc)

    db.add(
        JobStageHistory(
            tenant_id=auth.tenant_id,
            job_id=job.id,
            stage_before=stage_before,
            stage_after=body.new_stage.value,
            source="manual",
            rationale=body.reason,
        )
    )

    db.add(
        JobManualChange(
            tenant_id=auth.tenant_id,
            job_id=job.id,
            user_id=auth.user_id,
            stage_before=stage_before,
            stage_after=body.new_stage.value,
            reason=body.reason,
        )
    )

    db.add(
        JobEvent(
            tenant_id=auth.tenant_id,
            job_id=job.id,
            event_type=None,
            stage_before=stage_before,
            stage_after=body.new_stage.value,
            source="manual",
            rationale=body.reason,
        )
    )

    db.commit()
    db.refresh(job)
    return job
