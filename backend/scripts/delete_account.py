#!/usr/bin/env python3
"""Delete an account by UUID.

The UUID can be either:
- A tenant ID (tenants.id) — deletes the full tenant and all its data.
- An email account ID (email_accounts.id) — deletes that Gmail connection and its messages/extractions.

Usage (from backend directory, with venv activated):
  python scripts/delete_account.py e38ea9fd-60b7-470d-8236-ed723a855ec5

Or:
  python -m scripts.delete_account e38ea9fd-60b7-470d-8236-ed723a855ec5
"""
import sys
import uuid as uuid_lib
from pathlib import Path

# Allow importing app when run as script
backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.contact import Contact, ContactAffiliation, JobContact
from app.models.email_account import EmailAccount
from app.models.job import (
    Job,
    JobEvent,
    JobIdentity,
    JobManualChange,
    JobStageHistory,
    JobThread,
)
from app.models.llm_key import LlmKey
from app.models.merge_suggestion import JobMergeSuggestion
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.user import User


def delete_tenant(db: Session, tenant_id: uuid_lib.UUID) -> None:
    """Delete a tenant and all related data in FK-safe order."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")

    # Job child tables (reference jobs.id)
    db.query(JobManualChange).filter(JobManualChange.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobStageHistory).filter(JobStageHistory.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobEvent).filter(JobEvent.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobThread).filter(JobThread.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobIdentity).filter(JobIdentity.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobContact).filter(JobContact.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobMergeSuggestion).filter(JobMergeSuggestion.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Job).filter(Job.tenant_id == tenant_id).delete(synchronize_session=False)

    # Contact tables
    db.query(ContactAffiliation).filter(ContactAffiliation.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.tenant_id == tenant_id).delete(synchronize_session=False)

    # Message extractions and messages (tenant-scoped; messages also have account_id)
    db.query(MessageExtraction).filter(MessageExtraction.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Message).filter(Message.tenant_id == tenant_id).delete(synchronize_session=False)

    # Email accounts, users, settings, LLM keys
    db.query(EmailAccount).filter(EmailAccount.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).delete(synchronize_session=False)

    db.delete(tenant)
    db.commit()
    print(f"Deleted tenant {tenant_id} ({tenant.name}) and all related data.")


def delete_email_account(db: Session, account_id: uuid_lib.UUID) -> None:
    """Delete one email account and its messages/extractions (not tenant-wide jobs/contacts)."""
    account = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
    if not account:
        raise ValueError(f"Email account not found: {account_id}")

    # Messages for this account
    msg_ids = [row[0] for row in db.query(Message.id).filter(Message.account_id == account_id).all()]

    if msg_ids:
        # JobEvent and JobStageHistory reference messages.id and message_extractions.id; null FKs first
        extraction_ids = [
            row[0]
            for row in db.query(MessageExtraction.id).filter(
                MessageExtraction.message_id.in_(msg_ids)
            ).all()
        ]
        if extraction_ids:
            db.query(JobEvent).filter(
                JobEvent.extraction_id.in_(extraction_ids)
            ).update({JobEvent.extraction_id: None}, synchronize_session=False)
        db.query(JobEvent).filter(JobEvent.message_id.in_(msg_ids)).update(
            {JobEvent.message_id: None}, synchronize_session=False
        )
        db.query(JobStageHistory).filter(JobStageHistory.message_id.in_(msg_ids)).update(
            {JobStageHistory.message_id: None}, synchronize_session=False
        )
        db.query(MessageExtraction).filter(
            MessageExtraction.message_id.in_(msg_ids)
        ).delete(synchronize_session=False)

    db.query(Message).filter(Message.account_id == account_id).delete(synchronize_session=False)
    db.delete(account)
    db.commit()
    print(f"Deleted email account {account_id} ({account.email_address}) and its messages/extractions.")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/delete_account.py <uuid>", file=sys.stderr)
        sys.exit(1)

    try:
        target_id = uuid_lib.UUID(sys.argv[1])
    except ValueError:
        print(f"Invalid UUID: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        if db.query(Tenant).filter(Tenant.id == target_id).first():
            delete_tenant(db, target_id)
        elif db.query(EmailAccount).filter(EmailAccount.id == target_id).first():
            delete_email_account(db, target_id)
        else:
            print(f"No tenant or email account found with id {target_id}.", file=sys.stderr)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
