"""Shared logic for merging one job into another (used by merge suggestions and manual merge)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.contact import JobContact
from app.models.job import Job, JobEvent, JobIdentity, JobStageHistory, JobThread


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

    # Update target's last_activity to the latest of both
    if source.last_activity and (
        not target.last_activity or source.last_activity > target.last_activity
    ):
        target.last_activity = source.last_activity

    db.delete(source)
