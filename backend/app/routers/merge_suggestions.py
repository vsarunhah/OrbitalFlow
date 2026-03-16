"""Job merge suggestions: detect duplicates and allow merge action."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.job import Job
from app.models.merge_suggestion import JobMergeSuggestion
from app.schemas.merge_suggestion import (
    MergeApplyResult,
    MergeSuggestionJobSummary,
    MergeSuggestionListResponse,
    MergeSuggestionOut,
)
from app.services.job_merge import merge_job_into_target

router = APIRouter(prefix="/merge-suggestions", tags=["merge-suggestions"])


def _job_summary(job: Job) -> MergeSuggestionJobSummary:
    return MergeSuggestionJobSummary(
        id=job.id,
        company=job.company,
        role=job.role,
        current_stage=job.current_stage,
    )


@router.get("", response_model=MergeSuggestionListResponse)
def list_merge_suggestions(
    status_filter: str | None = Query(
        "pending", alias="status", description="Filter by status (pending, applied, dismissed)"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_q = db.query(JobMergeSuggestion).filter(
        JobMergeSuggestion.tenant_id == auth.tenant_id,
    )
    if status_filter:
        base_q = base_q.filter(JobMergeSuggestion.status == status_filter)

    total = base_q.count()

    rows = (
        base_q
        .order_by(JobMergeSuggestion.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for ms in rows:
        source_job = db.query(Job).filter(Job.id == ms.source_job_id).first()
        target_job = db.query(Job).filter(Job.id == ms.target_job_id).first()
        if not source_job or not target_job:
            continue
        items.append(
            MergeSuggestionOut(
                id=ms.id,
                source_job=_job_summary(source_job),
                target_job=_job_summary(target_job),
                reason=ms.reason,
                confidence=ms.confidence,
                status=ms.status,
                created_at=ms.created_at,
            )
        )

    return MergeSuggestionListResponse(items=items, total=total)


@router.post("/{suggestion_id}/apply", response_model=MergeApplyResult)
def apply_merge_suggestion(
    suggestion_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ms = (
        db.query(JobMergeSuggestion)
        .filter(
            JobMergeSuggestion.id == suggestion_id,
            JobMergeSuggestion.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not ms:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merge suggestion not found",
        )
    if ms.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Suggestion already {ms.status}",
        )

    source = db.query(Job).filter(Job.id == ms.source_job_id).first()
    target = db.query(Job).filter(Job.id == ms.target_job_id).first()
    if not source or not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One of the jobs no longer exists",
        )

    merge_job_into_target(db, source, target)

    # Mark suggestion as applied
    ms.status = "applied"
    ms.resolved_at = datetime.now(timezone.utc)

    db.commit()

    return MergeApplyResult(
        merged_job_id=target.id,
        removed_job_id=ms.source_job_id,
        status="applied",
    )
