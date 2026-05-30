"""Tests for AI reply drafts and send-from-app (human-in-the-loop)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.encryption import encrypt
from app.models.contact import Contact, JobContact
from app.models.draft import MessageDraft, SentMessage
from app.models.email_account import EmailAccount
from app.models.job import Job, JobEvent, JobThread
from app.models.llm_key import LlmKey
from app.models.message import Message
from app.models.user import User
from app.providers.base import SendResult
from app.schemas.draft import DraftReplyResult, ReplyVariantSchema


def _create_job_with_account_and_llm(db_session, tenant_id, user_id):
    """Create job, email_account, llm_key, job_thread, and a message so account is resolvable."""
    job = Job(
        tenant_id=tenant_id,
        company="Acme",
        role="SWE",
        current_stage="APPLIED",
    )
    db_session.add(job)
    db_session.flush()

    oauth_creds = json.dumps({
        "access_token": "fake",
        "refresh_token": "fake_refresh",
    })
    account = EmailAccount(
        tenant_id=tenant_id,
        email_address="me@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(oauth_creds),
    )
    db_session.add(account)
    db_session.flush()

    llm_key = LlmKey(
        tenant_id=tenant_id,
        provider="openai",
        encrypted_key=encrypt("sk-fake-openai-key"),
    )
    db_session.add(llm_key)
    db_session.flush()

    # Link job to thread so account can be resolved
    jt = JobThread(
        tenant_id=tenant_id,
        job_id=job.id,
        thread_id="thread-123",
    )
    db_session.add(jt)
    db_session.flush()

    msg = Message(
        tenant_id=tenant_id,
        account_id=account.id,
        provider_msg_id="msg-456",
        thread_id="thread-123",
        subject="Re: Role at Acme",
        from_address="recruiter@acme.com",
        to_addresses="me@example.com",
        body_text="Would you like to schedule a call?",
        raw_payload_json="{}",
    )
    db_session.add(msg)
    db_session.flush()

    return job, account, llm_key, msg


def _create_contact_for_job(db_session, tenant_id, job_id, email="recruiter@acme.com"):
    """Add a contact and job_contact so send has a recipient."""
    contact = Contact(
        tenant_id=tenant_id,
        name="Recruiter",
        email=email,
    )
    db_session.add(contact)
    db_session.flush()
    jc = JobContact(
        tenant_id=tenant_id,
        job_id=job_id,
        contact_id=contact.id,
        role="recruiter",
    )
    db_session.add(jc)
    db_session.flush()
    return contact


def _three_variants():
    """Return 3 variants for mocking generate_reply_variants."""
    return [
        ReplyVariantSchema(
            variant_id="concise",
            tone="concise",
            subject="Re: Role at Acme",
            body="Thank you, I would love to schedule a call.",
            confidence=0.9,
        ),
        ReplyVariantSchema(
            variant_id="warm",
            tone="warm",
            subject="Re: Role at Acme",
            body="Thanks so much for reaching out! I would really enjoy scheduling a call.",
            confidence=0.85,
        ),
        ReplyVariantSchema(
            variant_id="enthusiastic",
            tone="enthusiastic",
            subject="Re: Role at Acme",
            body="I am very excited and would love to schedule a call at your convenience!",
            confidence=0.88,
        ),
    ], {"job_id": "x"}


@pytest.fixture()
def db_session():
    from tests.conftest import TestSession
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


class TestDraftReplyCreate:
    """POST /jobs/{id}/draft-reply with mocked generate_reply_variants."""

    @patch("app.routers.drafts.generate_reply_variants")
    def test_create_draft_reply_success(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        db_session.commit()

        resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"tone": "professional"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft" in data
        assert "variants" in data
        draft_data = data["draft"]
        assert draft_data["subject"] == "Re: Role at Acme"
        assert "Thank you" in (draft_data["body_text"] or "")
        assert draft_data["status"] == "GENERATED"
        assert draft_data["job_id"] == str(job.id)
        assert draft_data["account_id"] == str(account.id)
        assert len(data["variants"]) == 3
        assert data["variants"][0]["variant_id"] == "concise"

        draft = db_session.query(MessageDraft).filter(MessageDraft.job_id == job.id).first()
        assert draft is not None
        assert draft.status == "GENERATED"
        assert draft.variants_json is not None

    @patch("app.routers.drafts.generate_reply_variants")
    def test_create_draft_reply_no_account_400(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job = Job(tenant_id=tenant_id, company="Acme", role="SWE", current_stage="APPLIED")
        db_session.add(job)
        db_session.add(
            LlmKey(tenant_id=tenant_id, provider="openai", encrypted_key=encrypt("sk-fake")),
        )
        db_session.commit()
        # No job_thread / message -> no account resolved

        resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={},
        )
        assert resp.status_code == 400
        assert "email account" in resp.json()["detail"].lower()


class TestDraftGetPatch:
    """GET and PATCH /drafts/{id}."""

    @patch("app.routers.drafts.generate_reply_variants")
    def test_get_and_patch_draft(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, _ = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"tone": "concise"},
        )
        assert create_resp.status_code == 200
        draft_id = create_resp.json()["draft"]["id"]

        get_resp = client.get(f"/drafts/{draft_id}", headers=auth_header)
        assert get_resp.status_code == 200
        assert get_resp.json()["subject"] == "Re: Role at Acme"
        assert get_resp.json().get("variants") is not None
        assert len(get_resp.json()["variants"]) == 3

        patch_resp = client.patch(
            f"/drafts/{draft_id}",
            headers=auth_header,
            json={"subject": "Re: Updated", "body_text": "Updated body"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["subject"] == "Re: Updated"
        assert patch_resp.json()["body_text"] == "Updated body"
        assert patch_resp.json()["status"] == "EDITED"


class TestClearJobDrafts:
    """DELETE /jobs/{id}/drafts removes unsent drafts only."""

    @patch("app.routers.drafts.generate_reply_variants")
    def test_clear_unsent_drafts_keeps_sent(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        first = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        assert first.status_code == 200

        second = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        assert second.status_code == 200
        sent_draft_id = uuid.UUID(first.json()["draft"]["id"])

        sent_draft = db_session.query(MessageDraft).filter(MessageDraft.id == sent_draft_id).first()
        assert sent_draft is not None
        sent_draft.status = "SENT"
        db_session.commit()

        clear_resp = client.delete(f"/jobs/{job.id}/drafts", headers=auth_header)
        assert clear_resp.status_code == 200
        assert clear_resp.json()["deleted_count"] == 1

        remaining = (
            db_session.query(MessageDraft)
            .filter(MessageDraft.job_id == job.id)
            .all()
        )
        assert len(remaining) == 1
        assert remaining[0].id == sent_draft_id
        assert remaining[0].status == "SENT"

        get_resp = client.get(f"/jobs/{job.id}/draft", headers=auth_header)
        assert get_resp.status_code == 404

    def test_clear_drafts_job_not_found(self, client, auth_header):
        resp = client.delete(f"/jobs/{uuid.uuid4()}/drafts", headers=auth_header)
        assert resp.status_code == 404


class TestDraftSend:
    """POST /drafts/{id}/send with mocked Gmail send."""

    @patch("app.routers.drafts.GmailProvider")
    @patch("app.routers.drafts.generate_reply_variants")
    def test_send_draft_success(self, mock_generate, mock_gmail_cls, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        mock_provider = mock_gmail_cls.return_value
        mock_provider.send_message.return_value = SendResult(
            provider_message_id="gmail-msg-1",
            thread_id="thread-123",
        )

        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id), "tone": "professional"},
        )
        assert create_resp.status_code == 200
        draft_id = create_resp.json()["draft"]["id"]

        send_resp = client.post(f"/drafts/{draft_id}/send", headers=auth_header)
        assert send_resp.status_code == 200
        assert send_resp.json()["status"] == "SENT"

        draft = db_session.query(MessageDraft).filter(MessageDraft.id == uuid.UUID(draft_id)).first()
        assert draft.status == "SENT"

        sent = db_session.query(SentMessage).filter(SentMessage.job_id == job.id).first()
        assert sent is not None
        assert sent.provider_message_id == "gmail-msg-1"
        assert "recruiter@acme.com" in sent.to_addrs_json

        event = db_session.query(JobEvent).filter(
            JobEvent.job_id == job.id,
            JobEvent.event_type == "REPLY_SENT",
        ).first()
        assert event is not None
        assert event.source == "send"

    @patch("app.routers.drafts.generate_reply_variants")
    def test_send_draft_already_sent_400(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        draft_id = create_resp.json()["draft"]["id"]

        with patch("app.routers.drafts.GmailProvider") as mock_gmail_cls:
            mock_gmail_cls.return_value.send_message.return_value = SendResult(
                provider_message_id="x", thread_id="y",
            )
            client.post(f"/drafts/{draft_id}/send", headers=auth_header)

        second_send = client.post(f"/drafts/{draft_id}/send", headers=auth_header)
        assert second_send.status_code == 400
        assert "already sent" in second_send.json()["detail"].lower()

    @patch("app.routers.drafts.generate_reply_variants")
    def test_get_draft_recipients_reply_all(self, mock_generate, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        draft_id = create_resp.json()["draft"]["id"]

        rec_resp = client.get(f"/drafts/{draft_id}/recipients", headers=auth_header)
        assert rec_resp.status_code == 200
        data = rec_resp.json()
        assert "to_addrs" in data
        assert "cc_addrs" in data
        assert data["to_addrs"] == ["recruiter@acme.com"]
        assert data["cc_addrs"] == []  # sender me@example.com excluded from CC

    @patch("app.routers.drafts.GmailProvider")
    @patch("app.routers.drafts.generate_reply_variants")
    def test_send_draft_with_recipient_override(self, mock_generate, mock_gmail_cls, client, auth_header, db_session):
        mock_generate.return_value = _three_variants()
        mock_gmail_cls.return_value.send_message.return_value = SendResult(
            provider_message_id="override-1", thread_id="thread-123",
        )
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        draft_id = create_resp.json()["draft"]["id"]

        send_resp = client.post(
            f"/drafts/{draft_id}/send",
            headers=auth_header,
            json={"to_addrs": ["only-this@example.com"], "cc_addrs": []},
        )
        assert send_resp.status_code == 200
        mock_gmail_cls.return_value.send_message.assert_called_once()
        call_kw = mock_gmail_cls.return_value.send_message.call_args[1]
        assert call_kw["to_addrs"] == ["only-this@example.com"]
        assert call_kw.get("cc_addrs") in (None, [])

    @patch("app.routers.drafts.GmailProvider")
    @patch("app.routers.drafts.generate_reply_variants")
    def test_send_draft_with_attachments_multipart(
        self, mock_generate, mock_gmail_cls, client, auth_header, db_session
    ):
        mock_generate.return_value = _three_variants()
        mock_gmail_cls.return_value.send_message.return_value = SendResult(
            provider_message_id="gmail-msg-att",
            thread_id="thread-123",
        )
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        create_resp = client.post(
            f"/jobs/{job.id}/draft-reply",
            headers=auth_header,
            json={"source_message_id": str(msg.id)},
        )
        draft_id = create_resp.json()["draft"]["id"]

        send_resp = client.post(
            f"/drafts/{draft_id}/send",
            headers=auth_header,
            data={
                "to_addrs": json.dumps(["recruiter@acme.com"]),
                "cc_addrs": json.dumps([]),
            },
            files=[
                ("attachments", ("notes.txt", b"hello attach", "text/plain")),
            ],
        )
        assert send_resp.status_code == 200
        assert send_resp.json()["status"] == "SENT"
        mock_gmail_cls.return_value.send_message.assert_called_once()
        call_kw = mock_gmail_cls.return_value.send_message.call_args[1]
        atts = call_kw.get("attachments")
        assert atts is not None and len(atts) == 1
        assert atts[0].filename == "notes.txt"
        assert atts[0].data == b"hello attach"

    def test_get_job_reply_recipients_without_draft(self, client, auth_header, db_session):
        """GET /jobs/{id}/reply-recipients returns default reply-all before any draft exists."""
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        rec_resp = client.get(
            f"/jobs/{job.id}/reply-recipients",
            headers=auth_header,
            params={"source_message_id": str(msg.id)},
        )
        assert rec_resp.status_code == 200
        data = rec_resp.json()
        assert data["to_addrs"] == ["recruiter@acme.com"]
        assert data["cc_addrs"] == []

    def test_create_compose_draft(self, client, auth_header, db_session):
        """POST /jobs/{id}/compose-draft creates a draft without AI."""
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, msg = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        _create_contact_for_job(db_session, tenant_id, job.id)
        db_session.commit()

        resp = client.post(
            f"/jobs/{job.id}/compose-draft",
            headers=auth_header,
            json={
                "source_message_id": str(msg.id),
                "subject": "Re: Quick question",
                "body_text": "Thanks, I will reply soon.",
            },
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["subject"] == "Re: Quick question"
        assert d["body_text"] == "Thanks, I will reply soon."
        assert d["job_id"] == str(job.id)
        assert d["source_message_id"] == str(msg.id)
        assert d["draft_type"] == "reply"
        assert d["status"] == "EDITED"


class TestResolveRecipientsReplyTo:
    """When replying in thread, prefer Reply-To header over From."""

    def test_reply_to_used_when_present(self, db_session):
        from app.models.tenant import Tenant

        from app.routers.drafts import _resolve_recipients_and_thread

        tenant = Tenant(name="T")
        db_session.add(tenant)
        db_session.flush()

        user = User(tenant_id=tenant.id, email="u@t.com", password_hash="x")
        db_session.add(user)
        db_session.flush()

        account = EmailAccount(
            tenant_id=tenant.id,
            email_address="me@example.com",
            provider="gmail",
            oauth_encrypted=encrypt('{"access_token":"x","refresh_token":"y"}'),
        )
        db_session.add(account)
        db_session.flush()

        # Message with Reply-To different from From (e.g. noreply@ with Reply-To to real person)
        msg = Message(
            tenant_id=tenant.id,
            account_id=account.id,
            provider_msg_id="m1",
            thread_id="thread-1",
            from_address="noreply@linkedin.com",
            to_addresses="me@example.com",
            headers_json=json.dumps({"reply-to": "Recruiter Name <recruiter@company.com>"}),
            body_text="Hello",
            raw_payload_json="{}",
        )
        db_session.add(msg)
        db_session.flush()

        job = Job(tenant_id=tenant.id, company="Co", role="SWE", current_stage="APPLIED")
        db_session.add(job)
        db_session.flush()

        draft = MessageDraft(
            tenant_id=tenant.id,
            job_id=job.id,
            account_id=account.id,
            source_message_id=msg.id,
            subject="Re: Hello",
            body_text="Hi",
            status="EDITED",
            created_by_user_id=user.id,
        )
        db_session.add(draft)
        db_session.flush()

        to_addrs, cc_addrs, thread_id = _resolve_recipients_and_thread(
            db_session, tenant.id, draft, sender_email=account.email_address
        )
        assert thread_id == "thread-1"
        assert to_addrs == ["recruiter@company.com"]
        assert cc_addrs == []  # reply-all excludes sender (me@example.com)

    def test_falls_back_to_from_when_no_reply_to(self, db_session):
        from app.models.tenant import Tenant

        from app.routers.drafts import _resolve_recipients_and_thread

        tenant = Tenant(name="T2")
        db_session.add(tenant)
        db_session.flush()

        user = User(tenant_id=tenant.id, email="u2@t.com", password_hash="x")
        db_session.add(user)
        db_session.flush()

        account = EmailAccount(
            tenant_id=tenant.id,
            email_address="me@example.com",
            provider="gmail",
            oauth_encrypted=encrypt('{"access_token":"x"}'),
        )
        db_session.add(account)
        db_session.flush()

        msg = Message(
            tenant_id=tenant.id,
            account_id=account.id,
            provider_msg_id="m2",
            thread_id="thread-2",
            from_address="Jane <jane@acme.com>",
            to_addresses="me@example.com",
            headers_json=json.dumps({"from": "Jane <jane@acme.com>"}),  # no reply-to
            body_text="Hi",
            raw_payload_json="{}",
        )
        db_session.add(msg)
        db_session.flush()

        job = Job(tenant_id=tenant.id, company="Acme", role="SWE", current_stage="APPLIED")
        db_session.add(job)
        db_session.flush()

        draft = MessageDraft(
            tenant_id=tenant.id,
            job_id=job.id,
            account_id=account.id,
            source_message_id=msg.id,
            subject="Re: Hi",
            body_text="Thanks",
            status="EDITED",
            created_by_user_id=user.id,
        )
        db_session.add(draft)
        db_session.flush()

        to_addrs, cc_addrs, _ = _resolve_recipients_and_thread(
            db_session, tenant.id, draft, sender_email=account.email_address
        )
        assert to_addrs == ["jane@acme.com"]
        assert cc_addrs == []  # reply-all excludes sender (me@example.com)


class TestReplyGenerationService:
    """Unit test for reply generation with mocked LLM."""

    @patch("app.services.reply_generation.get_llm_client")
    def test_generate_reply_returns_subject_and_body(self, mock_get_client, db_session):
        from app.models.tenant import Tenant

        tenant = Tenant(name="T")
        db_session.add(tenant)
        db_session.flush()

        job = Job(tenant_id=tenant.id, company="Acme", role="SWE", current_stage="INTERVIEW")
        db_session.add(job)
        db_session.flush()
        db_session.add(
            LlmKey(tenant_id=tenant.id, provider="openai", encrypted_key=encrypt("sk-fake")),
        )
        db_session.commit()

        from app.llm.base import LlmResponse

        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = LlmResponse(
            raw_text='{"subject": "Re: Interview", "body": "Thank you for the update. I look forward to it.", "tone": "professional", "confidence": 0.9}',
        )
        mock_get_client.return_value = mock_llm

        from app.services.reply_generation import generate_reply

        result, context = generate_reply(
            db_session, tenant.id, job.id,
            source_message_id=None,
            tone="professional",
            user_instruction=None,
            user_email="test@example.com",
        )
        assert result.subject == "Re: Interview"
        assert "look forward" in result.body
        assert result.tone == "professional"
        assert result.confidence == 0.9
        assert context["job_stage"] == "INTERVIEW"

    @patch("app.services.reply_generation.get_llm_client")
    def test_generate_reply_user_content_includes_thread_summary_when_messages_present(
        self, mock_get_client, db_session
    ):
        """When job has thread messages, user content passed to LLM includes thread summary."""
        from app.llm.base import LlmResponse
        from app.models.tenant import Tenant
        from app.models.email_account import EmailAccount

        tenant = Tenant(name="T")
        db_session.add(tenant)
        db_session.flush()
        job = Job(tenant_id=tenant.id, company="Acme", role="SWE", current_stage="APPLIED")
        db_session.add(job)
        db_session.flush()
        acc = EmailAccount(
            tenant_id=tenant.id,
            email_address="me@example.com",
            provider="gmail",
            oauth_encrypted=encrypt('{"access_token":"x","refresh_token":"y"}'),
        )
        db_session.add(acc)
        db_session.flush()
        jt = JobThread(tenant_id=tenant.id, job_id=job.id, thread_id="thread-1")
        db_session.add(jt)
        db_session.flush()
        msg = Message(
            tenant_id=tenant.id,
            account_id=acc.id,
            provider_msg_id="msg-1",
            thread_id="thread-1",
            from_address="recruiter@acme.com",
            body_text="Would you like to schedule a call?",
            raw_payload_json="{}",
        )
        db_session.add(msg)
        db_session.add(
            LlmKey(tenant_id=tenant.id, provider="openai", encrypted_key=encrypt("sk-fake")),
        )
        db_session.commit()

        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = LlmResponse(
            raw_text='{"subject": "Re: Call", "body": "Yes, I would.", "tone": "professional", "confidence": 0.85}',
        )
        mock_get_client.return_value = mock_llm

        from app.services.reply_generation import generate_reply

        generate_reply(
            db_session, tenant.id, job.id,
            source_message_id=msg.id,
            tone="professional",
            user_instruction=None,
            user_email="me@example.com",
        )
        call_kw = mock_llm.chat_json.call_args[1]
        user_content = call_kw.get("user_content") or ""
        assert "Thread summary" in user_content or "recent messages" in user_content.lower()
        assert "recruiter@acme.com" in user_content or "Would you like" in user_content
        assert "Acme" in user_content and "APPLIED" in user_content


class TestGenerateReplyVariants:
    """Unit tests for multi-variant reply generation."""

    @patch("app.services.reply_generation.get_llm_client")
    def test_generate_reply_variants_returns_three(self, mock_get_client, db_session):
        from app.models.tenant import Tenant

        tenant = Tenant(name="T")
        db_session.add(tenant)
        db_session.flush()
        job = Job(tenant_id=tenant.id, company="Acme", role="SWE", current_stage="APPLIED")
        db_session.add(job)
        db_session.flush()
        db_session.add(
            LlmKey(tenant_id=tenant.id, provider="openai", encrypted_key=encrypt("sk-fake")),
        )
        db_session.commit()

        from app.llm.base import LlmResponse

        raw = json.dumps({
            "variants": [
                {"variant_id": "concise", "tone": "concise", "subject": "Re: Hi", "body": "Short reply.", "confidence": 0.9},
                {"variant_id": "warm", "tone": "warm", "subject": "Re: Hi", "body": "Thanks so much!", "confidence": 0.85},
                {"variant_id": "enthusiastic", "tone": "enthusiastic", "subject": "Re: Hi", "body": "I am very excited!", "confidence": 0.88},
            ]
        })
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = LlmResponse(raw_text=raw)
        mock_get_client.return_value = mock_llm

        from app.services.reply_generation import generate_reply_variants

        variants, context = generate_reply_variants(
            db_session, tenant.id, job.id,
            source_message_id=None,
            user_instruction=None,
            user_email="test@example.com",
        )
        assert len(variants) == 3
        assert variants[0].variant_id == "concise"
        assert variants[0].body == "Short reply."
        assert variants[1].variant_id == "warm"
        assert variants[2].variant_id == "enthusiastic"
        assert context["job_stage"] == "APPLIED"


class TestTimelineSentMessages:
    """Timeline includes sent_messages."""

    def test_timeline_includes_sent_messages(self, client, auth_header, db_session):
        r = client.get("/auth/me", headers=auth_header)
        tenant_id = uuid.UUID(r.json()["tenant_id"])
        user_id = uuid.UUID(r.json()["user_id"])

        job, account, _, _ = _create_job_with_account_and_llm(db_session, tenant_id, user_id)
        db_session.commit()

        sent = SentMessage(
            tenant_id=tenant_id,
            job_id=job.id,
            account_id=account.id,
            provider="gmail",
            provider_message_id="gm-1",
            thread_id="t-1",
            to_addrs_json='["recruiter@acme.com"]',
            subject="Re: Interview",
            body_text="Thank you, I confirm.",
        )
        db_session.add(sent)
        db_session.commit()

        resp = client.get(f"/jobs/{job.id}/timeline", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert "sent_messages" in data
        assert len(data["sent_messages"]) == 1
        assert data["sent_messages"][0]["subject"] == "Re: Interview"
        assert data["sent_messages"][0]["provider_message_id"] == "gm-1"
