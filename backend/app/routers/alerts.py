"""Alerts feed: messages classified as ALERT, with pagination."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.llm.prompts import strip_quoted_replies
from app.models.job import JobEvent, JobStageHistory
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from pydantic import ValidationError

from app.schemas.alert import AlertItem, AlertJobListing, AlertListResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_q = db.query(Message).filter(
        Message.tenant_id == auth.tenant_id,
        Message.category == "ALERT",
    )

    total = base_q.count()

    rows = (
        base_q
        .order_by(Message.date_header.desc().nullslast(), Message.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    msg_ids = [m.id for m in rows]
    extractions = (
        db.query(MessageExtraction)
        .filter(
            MessageExtraction.message_id.in_(msg_ids),
            MessageExtraction.status == "completed",
        )
        .all()
    ) if msg_ids else []
    extraction_by_msg = {e.message_id: e for e in extractions}

    items = []
    for m in rows:
        raw = (m.body_text or "").strip()
        cleaned = strip_quoted_replies(raw) if raw else ""
        snippet = cleaned[:300] if cleaned else None

        jobs = []
        ext = extraction_by_msg.get(m.id)
        if ext and ext.alert_jobs_json:
            try:
                for j in json.loads(ext.alert_jobs_json):
                    try:
                        jobs.append(AlertJobListing(**j))
                    except ValidationError:
                        pass  # skip malformed job entries from extraction
            except (json.JSONDecodeError, TypeError):
                pass

        items.append(
            AlertItem(
                id=m.id,
                subject=m.subject,
                from_address=m.from_address,
                date_header=m.date_header,
                body_snippet=snippet,
                category=m.category,
                provider_msg_id=m.provider_msg_id,
                jobs=jobs,
            )
        )

    return AlertListResponse(items=items, total=total)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = (
        db.query(Message)
        .filter(
            Message.id == alert_id,
            Message.tenant_id == auth.tenant_id,
            Message.category == "ALERT",
        )
        .first()
    )
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    db.query(MessageExtraction).filter(
        MessageExtraction.message_id == alert_id
    ).delete()
    db.query(JobEvent).filter(JobEvent.message_id == alert_id).update(
        {JobEvent.message_id: None}
    )
    db.query(JobStageHistory).filter(
        JobStageHistory.message_id == alert_id
    ).update({JobStageHistory.message_id: None})

    db.delete(msg)
    db.commit()
    return None
