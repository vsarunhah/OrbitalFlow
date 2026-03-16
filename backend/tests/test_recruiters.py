"""Tests for recruiters API: message_count, company_count, primary_agency."""

from __future__ import annotations

import uuid

import pytest

from app.models.contact import Contact, ContactAffiliation, JobContact
from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent
from app.models.message import Message
from app.models.message_extraction import MessageExtraction


def _get_tenant_id(client, auth_header):
    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code == 200
    return uuid.UUID(r.json()["tenant_id"])


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def test_list_recruiters_returns_message_count_company_count_primary_agency(
    client, auth_header, db_session
):
    """List includes message_count, company_count, primary_agency from processed messages and affiliations."""
    tenant_id = _get_tenant_id(client, auth_header)

    # Contact with agency + company affiliations
    contact = Contact(
        tenant_id=tenant_id,
        email="recruiter@xyz-recruiting.com",
        name="Jane Recruiter",
    )
    db_session.add(contact)
    db_session.flush()

    db_session.add(
        ContactAffiliation(
            tenant_id=tenant_id,
            contact_id=contact.id,
            company="XYZ Recruiting",
            title="Recruiter",
            affiliation_type="agency",
        )
    )
    db_session.add(
        ContactAffiliation(
            tenant_id=tenant_id,
            contact_id=contact.id,
            company="Acme Corp",
            title=None,
            affiliation_type="company",
        )
    )

    job = Job(
        tenant_id=tenant_id,
        company="Beta Inc",
        role="SWE",
        current_stage="SOURCED",
    )
    db_session.add(job)
    db_session.flush()

    db_session.add(
        JobContact(
            tenant_id=tenant_id,
            job_id=job.id,
            contact_id=contact.id,
            role="recruiter",
        )
    )

    # Processed message from this recruiter (MessageExtraction links message to tenant)
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        provider="gmail",
        oauth_encrypted="dummy",
    )
    db_session.add(account)
    db_session.flush()

    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="msg-1",
        raw_payload_json="{}",
        from_address="Jane Recruiter <recruiter@xyz-recruiting.com>",
    )
    db_session.add(msg)
    db_session.flush()

    db_session.add(
        MessageExtraction(
            tenant_id=tenant_id,
            message_id=msg.id,
            category="RECRUITER",
            company="XYZ Recruiting",
        )
    )
    db_session.commit()

    r = client.get("/recruiters", headers=auth_header)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["email"] == "recruiter@xyz-recruiting.com"
    assert item["message_count"] == 1
    assert item["company_count"] == 3  # XYZ Recruiting, Acme Corp, Beta Inc
    assert item["primary_agency"] == "XYZ Recruiting"
    assert item["job_count"] == 1


def test_get_recruiter_detail_returns_relationship_fields(
    client, auth_header, db_session
):
    """Detail includes message_count, company_count, primary_agency, companies list."""
    tenant_id = _get_tenant_id(client, auth_header)

    contact = Contact(
        tenant_id=tenant_id,
        email="r2@staffing.com",
        name="Bob",
    )
    db_session.add(contact)
    db_session.flush()

    db_session.add(
        ContactAffiliation(
            tenant_id=tenant_id,
            contact_id=contact.id,
            company="Staffing Co",
            affiliation_type="agency",
        )
    )
    job = Job(
        tenant_id=tenant_id,
        company="Employer A",
        role="Engineer",
        current_stage="SOURCED",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        JobContact(tenant_id=tenant_id, job_id=job.id, contact_id=contact.id)
    )

    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        provider="gmail",
        oauth_encrypted="dummy",
    )
    db_session.add(account)
    db_session.flush()
    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="msg-2",
        raw_payload_json="{}",
        from_address="r2@staffing.com",
    )
    db_session.add(msg)
    db_session.flush()
    db_session.add(
        MessageExtraction(
            tenant_id=tenant_id,
            message_id=msg.id,
            category="RECRUITER",
        )
    )
    db_session.add(
        JobEvent(
            tenant_id=tenant_id,
            job_id=job.id,
            message_id=msg.id,
        )
    )
    db_session.commit()

    r = client.get(f"/recruiters/{contact.id}", headers=auth_header)
    assert r.status_code == 200
    data = r.json()
    assert data["message_count"] == 1
    assert data["company_count"] == 2  # Staffing Co, Employer A
    assert data["primary_agency"] == "Staffing Co"
    assert set(data["companies"]) == {"Employer A", "Staffing Co"}


def test_message_count_only_counts_processed_messages(
    client, auth_header, db_session
):
    """Messages that are not in MessageExtraction or JobEvent do not count."""
    tenant_id = _get_tenant_id(client, auth_header)

    contact = Contact(
        tenant_id=tenant_id,
        email="only@raw.com",
        name="Raw Only",
    )
    db_session.add(contact)
    db_session.flush()

    job = Job(
        tenant_id=tenant_id,
        company="C",
        role="R",
        current_stage="SOURCED",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        JobContact(tenant_id=tenant_id, job_id=job.id, contact_id=contact.id)
    )

    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@test.com",
        provider="gmail",
        oauth_encrypted="dummy",
    )
    db_session.add(account)
    db_session.flush()

    # Message with from_address = contact but NO extraction or job_event
    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="msg-raw",
        raw_payload_json="{}",
        from_address="only@raw.com",
    )
    db_session.add(msg)
    db_session.commit()

    r = client.get("/recruiters", headers=auth_header)
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["email"] == "only@raw.com")
    assert item["message_count"] == 0
