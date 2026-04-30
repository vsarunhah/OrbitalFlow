"""Shared logic for merging one job into another (used by merge suggestions and manual merge)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.contact import JobContact
from app.models.draft import MessageDraft, SentMessage
from app.models.job import (
    Job,
    JobEvent,
    JobIdentity,
    JobManualChange,
    JobStageHistory,
    JobThread,
    JobTimelineReadState,
)


def merge_job_into_target(
    db: Session,
    source: Job,
    target: Job,
) -> None:
    """Merge source job into target: move all related rows to target, then delete source."""
    if source.id == target.id:
        return

    # Re-point all events from source to target
    db.query(JobEvent).filter(JobEvent.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )

    # Re-point threads from source to target (skip conflicts)
    source_threads = db.query(JobThread).filter(JobThread.job_id == source.id).all()
    existing_target_threads = {
        t.thread_id
        for t in db.query(JobThread).filter(JobThread.job_id == target.id).all()
    }
    for t in source_threads:
        if t.thread_id in existing_target_threads:
            db.delete(t)
        else:
            t.job_id = target.id

    # Flush so thread updates hit the DB before we delete source (avoids NOT NULL violation)
    db.flush()

    # Re-point stage history
    db.query(JobStageHistory).filter(JobStageHistory.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )

    # Re-point job_contacts: source job's recruiters become linked to target job
    # Avoid duplicate (tenant_id, job_id, contact_id): if target already has that contact, delete source row
    source_jcs = db.query(JobContact).filter(JobContact.job_id == source.id).all()
    target_contact_ids = {
        jc.contact_id
        for jc in db.query(JobContact).filter(JobContact.job_id == target.id).all()
    }
    for jc in source_jcs:
        if jc.contact_id in target_contact_ids:
            db.delete(jc)
        else:
            jc.job_id = target.id

    # Flush so all FKs point to target before deleting source
    db.flush()

    # Re-point job_identities
    db.query(JobIdentity).filter(JobIdentity.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )

    # Re-point message_drafts and sent_messages so source job can be deleted
    db.query(MessageDraft).filter(MessageDraft.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )
    db.query(SentMessage).filter(SentMessage.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )

    # Re-point manual override audit rows so the source job can be deleted
    db.query(JobManualChange).filter(JobManualChange.job_id == source.id).update(
        {"job_id": target.id}, synchronize_session=False
    )

    db.flush()

    # Update target's last_activity to the latest of both
    if source.last_activity and (
        not target.last_activity or source.last_activity > target.last_activity
    ):
        target.last_activity = source.last_activity

    _merge_timeline_read_states(db, source, target)

    db.delete(source)


def _merge_timeline_read_states(db: Session, source: Job, target: Job) -> None:
    """Per user, take min(source.last_seen_at, target.last_seen_at). Missing row means
    "never opened" and dominates: if either side has no row for this user, the merged
    state is also "never opened" (delete target's row if any). Source's row is removed
    via FK cascade when source is deleted, so we only mutate target-side rows here.
    """
    source_states = {
        (s.tenant_id, s.user_id): s
        for s in db.query(JobTimelineReadState)
        .filter(JobTimelineReadState.job_id == source.id)
        .all()
    }
    target_states = {
        (t.tenant_id, t.user_id): t
        for t in db.query(JobTimelineReadState)
        .filter(JobTimelineReadState.job_id == target.id)
        .all()
    }

    all_keys = set(source_states.keys()) | set(target_states.keys())
    for key in all_keys:
        src = source_states.get(key)
        tgt = target_states.get(key)
        if src is None and tgt is not None:
            db.delete(tgt)
            continue
        if src is not None and tgt is not None:
            s_ts = src.last_seen_at
            t_ts = tgt.last_seen_at
            if s_ts is not None and s_ts.tzinfo is None:
                s_ts = s_ts.replace(tzinfo=timezone.utc)
            if t_ts is not None and t_ts.tzinfo is None:
                t_ts = t_ts.replace(tzinfo=timezone.utc)
            tgt.last_seen_at = min(s_ts, t_ts)
            # Avoid stale per-message dismiss on merged thread
            tgt.needs_reply_dismissed_up_to_message_id = None
    db.flush()
