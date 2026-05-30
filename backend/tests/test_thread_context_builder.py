"""Tests for thread context builder (structured context for AI reply generation)."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from app.models.contact import Contact, JobContact
from app.models.job import Job, JobThread
from app.models.message import Message
from app.models.tenant import Tenant
from app.llm.prompts import build_reply_user_content_from_context
from app.services.thread_context_builder import (
    THREAD_MESSAGE_BODY_MAX_CHARS,
    THREAD_TOTAL_BODY_BUDGET_CHARS,
    build_reply_context,
)


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _make_tenant_and_job(db_session):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    job = Job(
        tenant_id=tenant.id,
        company="Acme",
        role="SWE",
        current_stage="INTERVIEW",
    )
    db_session.add(job)
    db_session.flush()
    return tenant, job


def test_build_context_no_thread_returns_empty_thread_messages(db_session):
    """With no job_threads and no source_message_id, thread_messages is empty."""
    tenant, job = _make_tenant_and_job(db_session)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=None,
        tone="professional",
        user_instruction=None,
        user_email="me@example.com",
    )
    assert ctx.thread_messages == []
    assert ctx.job_company == "Acme"
    assert ctx.job_role == "SWE"
    assert ctx.job_stage == "INTERVIEW"
    assert ctx.user_name == "me@example.com"
    assert ctx.tone == "professional"
    assert "Recipient not specified" in ctx.recipient_info


def test_build_context_with_thread_returns_last_n_messages_chronological(db_session):
    """Thread with 3 messages returns all 3 in chronological order."""
    from app.models.email_account import EmailAccount
    from app.encryption import encrypt
    import json

    tenant, job = _make_tenant_and_job(db_session)
    acc = EmailAccount(
        tenant_id=tenant.id,
        email_address="u@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
    )
    db_session.add(acc)
    db_session.flush()

    jt = JobThread(tenant_id=tenant.id, job_id=job.id, thread_id="thread-1")
    db_session.add(jt)
    db_session.flush()

    base = datetime(2025, 3, 1, 12, 0, tzinfo=timezone.utc)
    for i in range(3):
        msg = Message(
            tenant_id=tenant.id,
            account_id=acc.id,
            provider_msg_id=f"msg-{i}",
            thread_id="thread-1",
            from_address=f"sender{i}@acme.com",
            date_header=base.replace(day=1 + i),
            body_text=f"Message body number {i}.",
            raw_payload_json="{}",
        )
        db_session.add(msg)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=None,
        tone="warm",
        user_instruction=None,
        user_email="me@example.com",
    )
    assert len(ctx.thread_messages) == 3
    assert ctx.thread_messages[0].sender == "sender0@acme.com"
    assert ctx.thread_messages[1].sender == "sender1@acme.com"
    assert ctx.thread_messages[2].sender == "sender2@acme.com"
    assert "Message body number 0" in ctx.thread_messages[0].body_text
    assert "Message body number 2" in ctx.thread_messages[2].body_text
    assert ctx.tone == "warm"


def test_build_context_includes_all_messages_in_thread(db_session):
    """Every message in the thread is included (not only the last N)."""
    from app.models.email_account import EmailAccount
    from app.encryption import encrypt
    import json

    tenant, job = _make_tenant_and_job(db_session)
    acc = EmailAccount(
        tenant_id=tenant.id,
        email_address="u@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
    )
    db_session.add(acc)
    db_session.flush()

    jt = JobThread(tenant_id=tenant.id, job_id=job.id, thread_id="thread-2")
    db_session.add(jt)
    db_session.flush()

    base = datetime(2025, 3, 1, 12, 0, tzinfo=timezone.utc)
    n = 12
    for i in range(n):
        msg = Message(
            tenant_id=tenant.id,
            account_id=acc.id,
            provider_msg_id=f"msg-{i}",
            thread_id="thread-2",
            from_address=f"u{i}@x.com",
            date_header=base.replace(day=1 + i),
            body_text=f"Body {i}",
            raw_payload_json="{}",
        )
        db_session.add(msg)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=None,
        tone="professional",
        user_instruction=None,
        user_email=None,
    )
    assert len(ctx.thread_messages) == n
    assert "Body 0" in ctx.thread_messages[0].body_text
    assert "Body 11" in ctx.thread_messages[-1].body_text


def test_build_context_body_truncated_per_message(db_session):
    """Each message body is truncated to THREAD_MESSAGE_BODY_MAX_CHARS."""
    from app.models.email_account import EmailAccount
    from app.encryption import encrypt
    import json

    tenant, job = _make_tenant_and_job(db_session)
    acc = EmailAccount(
        tenant_id=tenant.id,
        email_address="u@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
    )
    db_session.add(acc)
    db_session.flush()

    jt = JobThread(tenant_id=tenant.id, job_id=job.id, thread_id="thread-3")
    db_session.add(jt)
    db_session.flush()

    long_body = "x" * (THREAD_MESSAGE_BODY_MAX_CHARS + 100)
    msg = Message(
        tenant_id=tenant.id,
        account_id=acc.id,
        provider_msg_id="msg-long",
        thread_id="thread-3",
        from_address="a@b.com",
        body_text=long_body,
        raw_payload_json="{}",
    )
    db_session.add(msg)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=None,
        tone="professional",
        user_instruction=None,
        user_email="u@example.com",
    )
    assert len(ctx.thread_messages) == 1
    assert len(ctx.thread_messages[0].body_text) <= THREAD_MESSAGE_BODY_MAX_CHARS + 50  # + "[...truncated...]"
    assert "[...truncated...]" in ctx.thread_messages[0].body_text


def test_build_context_source_message_uses_that_thread(db_session):
    """When source_message_id is provided, use that message's thread for messages."""
    from app.models.email_account import EmailAccount
    from app.encryption import encrypt
    import json

    tenant, job = _make_tenant_and_job(db_session)
    acc = EmailAccount(
        tenant_id=tenant.id,
        email_address="u@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(json.dumps({"access_token": "x", "refresh_token": "y"})),
    )
    db_session.add(acc)
    db_session.flush()

    # Job linked to thread-A; we'll add source message in thread-B
    jt = JobThread(tenant_id=tenant.id, job_id=job.id, thread_id="thread-A")
    db_session.add(jt)
    db_session.flush()

    msg_in_b = Message(
        tenant_id=tenant.id,
        account_id=acc.id,
        provider_msg_id="msg-in-b",
        thread_id="thread-B",
        from_address="recruiter@acme.com",
        body_text="Reply to this thread B.",
        raw_payload_json="{}",
    )
    db_session.add(msg_in_b)
    db_session.flush()
    source_id = msg_in_b.id

    # One message in thread-B
    msg2 = Message(
        tenant_id=tenant.id,
        account_id=acc.id,
        provider_msg_id="msg2-in-b",
        thread_id="thread-B",
        from_address="me@example.com",
        body_text="My previous reply.",
        raw_payload_json="{}",
    )
    db_session.add(msg2)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=source_id,
        tone="professional",
        user_instruction="say I'm interested",
        user_email="me@example.com",
    )
    # Should use thread-B (source message's thread)
    assert len(ctx.thread_messages) >= 1
    assert any("Reply to this thread B" in m.body_text or "My previous reply" in m.body_text for m in ctx.thread_messages)
    assert ctx.user_instruction == "say I'm interested"


def test_build_context_recipient_info_from_contacts(db_session):
    """Recipient info is built from job contacts."""
    tenant, job = _make_tenant_and_job(db_session)
    contact = Contact(tenant_id=tenant.id, name="Jane", email="jane@acme.com")
    db_session.add(contact)
    db_session.flush()
    jc = JobContact(tenant_id=tenant.id, job_id=job.id, contact_id=contact.id, role="recruiter")
    db_session.add(jc)
    db_session.commit()

    ctx = build_reply_context(
        db_session,
        tenant_id=tenant.id,
        job_id=job.id,
        source_message_id=None,
        tone="direct",
        user_instruction=None,
        user_email="me@example.com",
    )
    assert "Jane" in ctx.recipient_info
    assert "jane@acme.com" in ctx.recipient_info
    assert "recruiter" in ctx.recipient_info
    assert ctx.tone == "direct"


def test_build_reply_user_content_from_context_format():
    """Prompt built from context has thread summary first, safety rules, and JSON format."""
    context = {
        "thread_messages": [
            {"sender": "a@b.com", "timestamp": "2025-03-01 12:00", "body_text": "Hello"},
        ],
        "job_company": "Acme",
        "job_role": "SWE",
        "job_stage": "INTERVIEW",
        "recipient_info": "- Jane <jane@acme.com> (recruiter)",
        "user_name": "me@example.com",
        "tone": "professional",
        "user_instruction": None,
    }
    content = build_reply_user_content_from_context(context)
    assert "Full thread" in content
    assert content.index("Full thread") < content.index("Job:")
    assert "a@b.com" in content and "Hello" in content
    assert "Acme" in content and "INTERVIEW" in content
    assert "Do not invent facts" in content
    assert "Do not promise specific times" in content or "availability" in content
    assert '"subject"' in content and '"body"' in content and '"confidence"' in content


def test_build_context_job_not_found_raises(db_session):
    tenant, job = _make_tenant_and_job(db_session)
    db_session.commit()
    fake_job_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Job not found"):
        build_reply_context(
            db_session,
            tenant_id=tenant.id,
            job_id=fake_job_id,
            source_message_id=None,
            tone="professional",
            user_instruction=None,
            user_email="u@example.com",
        )
