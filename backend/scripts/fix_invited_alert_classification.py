#!/usr/bin/env python3
"""Fix messages misclassified as interview invites that are actually job-board alerts.

Finds messages with subjects like "You are Invited! Senior Software Engineer - 03/17/2026"
(currently classified as STATUS/INTERVIEW_*) and reclassifies them as ALERT/JOB_ALERT so they
appear in the Alerts feed instead of as interview-related jobs.

Usage (from backend directory, with venv activated):
  python scripts/fix_invited_alert_classification.py
  python scripts/fix_invited_alert_classification.py "You are Invited!"

Or with a subject substring:
  python -m scripts.fix_invited_alert_classification "Senior Software Engineer"
"""
import json
import re
import sys
from pathlib import Path

# Allow importing app when run as script
backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.job import JobEvent, JobStageHistory
from app.models.message import Message
from app.models.message_extraction import MessageExtraction


def parse_role_from_invited_subject(subject: str) -> str | None:
    """Extract role/title from subject like 'You are Invited! Senior Software Engineer - 03/17/2026'."""
    subject = (subject or "").strip()
    if not subject:
        return None
    m = re.search(
        r"(?:you\s+are\s+invited!?|you're\s+invited)\s*[:\s]*([^-]+?)(?:\s*-\s*[\d/]+\s*)?$",
        subject,
        re.IGNORECASE,
    )
    if m:
        role = m.group(1).strip()
        return role if len(role) <= 255 else role[:255]
    return None


def fix_message(db: Session, msg: Message) -> bool:
    """Reclassify one message to ALERT/JOB_ALERT and unlink from jobs. Returns True if changed."""
    changed = False

    # Update message category so it appears in Alerts list
    if msg.category != "ALERT":
        msg.category = "ALERT"
        changed = True

    # Update all extractions for this message
    extractions = (
        db.query(MessageExtraction)
        .filter(MessageExtraction.message_id == msg.id)
        .all()
    )
    role_from_subject = parse_role_from_invited_subject(msg.subject or "")
    for ext in extractions:
        if ext.category != "ALERT" or ext.event_type != "JOB_ALERT":
            ext.category = "ALERT"
            ext.event_type = "JOB_ALERT"
            changed = True
        if not ext.alert_jobs_json and role_from_subject:
            ext.alert_jobs_json = json.dumps([{"role": role_from_subject}])
            changed = True

    # Unlink from job timeline so it only appears under Alerts
    n_events = (
        db.query(JobEvent)
        .filter(JobEvent.message_id == msg.id)
        .update({JobEvent.message_id: None})
    )
    n_history = (
        db.query(JobStageHistory)
        .filter(JobStageHistory.message_id == msg.id)
        .update({JobStageHistory.message_id: None})
    )
    if n_events or n_history:
        changed = True

    return changed


def main() -> None:
    subject_substring = (sys.argv[1] if len(sys.argv) > 1 else "You are Invited!").strip()
    if not subject_substring:
        print("Usage: fix_invited_alert_classification.py [subject_substring]")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Find messages that look like job-board "invited" alerts but are not already ALERT
        candidates = (
            db.query(Message)
            .filter(
                Message.subject.ilike(f"%{subject_substring}%"),
                Message.category != "ALERT",
            )
            .all()
        )
        if not candidates:
            print(f"No messages found with subject containing {subject_substring!r} and category != ALERT.")
            return

        print(f"Found {len(candidates)} message(s) to reclassify:")
        for msg in candidates:
            print(f"  id={msg.id} subject={msg.subject[:80]!r} from={msg.from_address} category={msg.category}")

        for msg in candidates:
            if fix_message(db, msg):
                print(f"Updated message id={msg.id} -> ALERT/JOB_ALERT")
        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
