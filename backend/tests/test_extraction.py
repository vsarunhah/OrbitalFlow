"""Tests for Phase 5: LLM extraction schemas and extraction service."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    Category,
    ContactInfo,
    EventType,
    ExtractionResult,
)


# ---------------------------------------------------------------------------
# ExtractionResult schema validation
# ---------------------------------------------------------------------------

def _valid_payload(**overrides) -> dict:
    base = {
        "category": "STATUS",
        "event_type": "APPLICATION_RECEIVED",
        "company": "Acme Corp",
        "role": "Software Engineer",
        "req_id": "REQ-123",
        "contacts": [{"name": "Alice", "email": "alice@acme.com", "role": "Recruiter"}],
        "confidence": 0.95,
        "rationale": "Email confirms application was received.",
    }
    base.update(overrides)
    return base


class TestExtractionResultSchema:
    def test_valid_full_payload(self):
        result = ExtractionResult.model_validate(_valid_payload())
        assert result.category == Category.STATUS
        assert result.event_type == EventType.APPLICATION_RECEIVED
        assert result.company == "Acme Corp"
        assert result.role == "Software Engineer"
        assert result.req_id == "REQ-123"
        assert len(result.contacts) == 1
        assert result.contacts[0].name == "Alice"
        assert result.confidence == 0.95

    def test_valid_minimal_payload(self):
        result = ExtractionResult.model_validate({
            "category": "OTHER",
            "event_type": "NONE",
            "confidence": 0.1,
            "rationale": "Not job related.",
        })
        assert result.company is None
        assert result.contacts == []

    def test_all_categories(self):
        for cat in Category:
            r = ExtractionResult.model_validate(
                _valid_payload(category=cat.value)
            )
            assert r.category == cat

    def test_all_event_types(self):
        for et in EventType:
            r = ExtractionResult.model_validate(
                _valid_payload(event_type=et.value)
            )
            assert r.event_type == et

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(category="INVALID")
            )

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(event_type="MADE_UP_EVENT")
            )

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(confidence=-0.1)
            )

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(confidence=1.5)
            )

    def test_missing_required_field_rejected(self):
        payload = _valid_payload()
        del payload["rationale"]
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(payload)

    def test_contacts_empty_list_ok(self):
        r = ExtractionResult.model_validate(_valid_payload(contacts=[]))
        assert r.contacts == []

    def test_contacts_partial_fields(self):
        r = ExtractionResult.model_validate(
            _valid_payload(contacts=[{"email": "bob@co.com"}])
        )
        assert r.contacts[0].email == "bob@co.com"
        assert r.contacts[0].name is None

    def test_roundtrip_json_serialization(self):
        result = ExtractionResult.model_validate(_valid_payload())
        as_json = result.model_dump_json()
        roundtrip = ExtractionResult.model_validate_json(as_json)
        assert roundtrip == result

    def test_company_max_length(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(company="X" * 256)
            )

    def test_rationale_max_length(self):
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(
                _valid_payload(rationale="X" * 513)
            )


# ---------------------------------------------------------------------------
# Extraction service: missing key behavior
# ---------------------------------------------------------------------------

class TestExtractionServiceMissingKey:
    """Test that extraction gracefully handles missing / unconfigured LLM keys."""

    def test_no_llm_key_marks_extraction_failed(self):
        """When no LLM key is configured for the tenant, extraction should
        create a row with status='failed' and error_reason='llm_key_not_configured',
        and set the message's extraction_status to 'extraction_failed'."""
        from tests.conftest import TestSession, engine
        from app.database import Base

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.message_extraction import MessageExtraction
            from app.services.extraction import run_extraction

            tenant = Tenant(name="TestCo")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_001",
                subject="Your Application to Acme",
                body_text="We received your application.",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "failed"
            assert extraction.error_reason == "llm_key_not_configured"

            db.refresh(msg)
            assert msg.extraction_status == "extraction_failed"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_llm_api_error_marks_extraction_failed(self):
        """When the LLM call raises an exception on all retries, extraction
        should be marked as failed with a descriptive error."""
        from tests.conftest import TestSession, engine
        from app.database import Base

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo2")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user2@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_002",
                subject="Interview Invite",
                body_text="Please schedule your interview.",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.side_effect = RuntimeError("API unreachable")

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "failed"
            assert "extraction_failed_after_2_attempts" in extraction.error_reason

            db.refresh(msg)
            assert msg.extraction_status == "extraction_failed"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_invalid_llm_json_retried_then_fails(self):
        """When the LLM returns invalid JSON on all attempts, extraction fails."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo3")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user3@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_003",
                subject="Offer Letter",
                body_text="Congratulations!",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            bad_response = LlmResponse(
                raw_text='{"category": "INVALID_VALUE"}',
                prompt_tokens=10,
                completion_tokens=5,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = bad_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "failed"
            assert "ValidationError" in extraction.error_reason
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_successful_extraction_persists(self):
        """When the LLM returns valid JSON, extraction is persisted correctly."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo4")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user4@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_004",
                subject="Application Received - Acme Corp",
                body_text="Thank you for applying to the Software Engineer position.",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            valid_json = json.dumps({
                "category": "STATUS",
                "event_type": "APPLICATION_RECEIVED",
                "company": "Acme Corp",
                "role": "Software Engineer",
                "req_id": "REQ-456",
                "contacts": [{"name": "HR Bot", "email": "hr@acme.com"}],
                "confidence": 0.92,
                "rationale": "Confirmation email for submitted application.",
            })
            good_response = LlmResponse(
                raw_text=valid_json,
                prompt_tokens=150,
                completion_tokens=80,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "STATUS"
            assert extraction.event_type == "APPLICATION_RECEIVED"
            assert extraction.company == "Acme Corp"
            assert extraction.role == "Software Engineer"
            assert extraction.req_id == "REQ-456"
            assert extraction.confidence == 0.92
            assert extraction.llm_provider == "openai"
            assert extraction.prompt_tokens == 150
            assert extraction.completion_tokens == 80

            db.refresh(msg)
            assert msg.category == "STATUS"
            assert msg.extraction_status == "completed"

            contacts = json.loads(extraction.contacts_json)
            assert len(contacts) == 1
            assert contacts[0]["name"] == "HR Bot"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_alert_override_empty_jobs_low_confidence(self):
        """When LLM returns ALERT with empty jobs and confidence < 0.85, override to OTHER so message does not appear on alerts page."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo5")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user5@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_005",
                subject="Your weekly digest",
                body_text="News from your network.",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            # LLM returns ALERT but no job listings and low confidence (e.g. marketing digest)
            alert_low_conf_json = json.dumps({
                "category": "ALERT",
                "event_type": "JOB_ALERT",
                "company": None,
                "role": None,
                "req_id": None,
                "contacts": [],
                "confidence": 0.7,
                "rationale": "Digest-style email.",
                "jobs": [],
            })
            good_response = LlmResponse(
                raw_text=alert_low_conf_json,
                prompt_tokens=100,
                completion_tokens=50,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "OTHER"
            assert extraction.event_type == "NONE"

            db.refresh(msg)
            assert msg.category == "OTHER"
            assert msg.extraction_status == "completed"
            # Message would not appear in GET /alerts since category != "ALERT"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_alert_not_overridden_when_has_jobs(self):
        """When LLM returns ALERT with at least one job listing, do not override even if confidence is low."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo6")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user6@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_006",
                subject="New jobs for you",
                body_text="Software Engineer at Acme...",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            alert_with_jobs_json = json.dumps({
                "category": "ALERT",
                "event_type": "JOB_ALERT",
                "company": None,
                "role": None,
                "req_id": None,
                "contacts": [],
                "confidence": 0.7,
                "rationale": "Job digest with one listing.",
                "jobs": [{"company": "Acme", "role": "Software Engineer", "location": "NYC", "url": "https://example.com/job/1"}],
            })
            good_response = LlmResponse(
                raw_text=alert_with_jobs_json,
                prompt_tokens=100,
                completion_tokens=60,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "ALERT"
            assert extraction.event_type == "JOB_ALERT"
            db.refresh(msg)
            assert msg.category == "ALERT"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_alert_not_overridden_high_confidence(self):
        """When LLM returns ALERT with empty jobs but confidence >= 0.85, do not override (trust the model)."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo7")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user7@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_007",
                subject="Job digest",
                body_text="No parseable listings in body.",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            alert_high_conf_json = json.dumps({
                "category": "ALERT",
                "event_type": "JOB_ALERT",
                "company": None,
                "role": None,
                "req_id": None,
                "contacts": [],
                "confidence": 0.9,
                "rationale": "Job board digest format.",
                "jobs": [],
            })
            good_response = LlmResponse(
                raw_text=alert_high_conf_json,
                prompt_tokens=100,
                completion_tokens=50,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "ALERT"
            assert extraction.event_type == "JOB_ALERT"
            db.refresh(msg)
            assert msg.category == "ALERT"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_linkedin_message_notification_override_recruiter_to_other(self):
        """LinkedIn 'X just messaged you' notifications must not be treated as RECRUITER (no job created)."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo8")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user8@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_008",
                subject="Ankit just messaged you",
                body_text="You have 1 new message\n\nAnkit Madan (Software Engineering Leadership)",
                from_address="Ankit Madan via LinkedIn <messaging-digest-noreply@linkedin.com>",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            # LLM incorrectly returns RECRUITER (e.g. "message notification from a recruiter")
            recruiter_json = json.dumps({
                "category": "RECRUITER",
                "event_type": "FOLLOW_UP",
                "company": None,
                "role": None,
                "req_id": None,
                "contacts": [{"name": "Ankit Madan", "email": None, "role": None}],
                "confidence": 0.8,
                "rationale": "The email is a message notification from a recruiter, indicating outreach but not tied to a specific application.",
                "jobs": [],
            })
            good_response = LlmResponse(
                raw_text=recruiter_json,
                prompt_tokens=100,
                completion_tokens=60,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "OTHER"
            assert extraction.event_type == "NONE"
            db.refresh(msg)
            assert msg.category == "OTHER"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    def test_job_board_invited_subject_override_interview_to_alert(self):
        """'You are Invited! [Role] - [Date]' from job-board domains must be ALERT/JOB_ALERT, not interview."""
        from tests.conftest import TestSession, engine
        from app.database import Base
        from app.llm.base import LlmResponse

        Base.metadata.create_all(bind=engine)
        db = TestSession()

        try:
            from app.models.tenant import Tenant
            from app.models.email_account import EmailAccount
            from app.models.message import Message
            from app.models.llm_key import LlmKey
            from app.services.extraction import run_extraction
            from app.encryption import encrypt

            tenant = Tenant(name="TestCo9")
            db.add(tenant)
            db.flush()

            account = EmailAccount(
                tenant_id=tenant.id,
                email_address="user9@test.com",
                provider="gmail",
                oauth_encrypted="encrypted_data",
                sync_cursor_json="{}",
            )
            db.add(account)
            db.flush()

            llm_key = LlmKey(
                tenant_id=tenant.id,
                provider="openai",
                encrypted_key=encrypt("sk-fake-key"),
            )
            db.add(llm_key)
            db.flush()

            msg = Message(
                tenant_id=tenant.id,
                account_id=account.id,
                provider_msg_id="msg_009",
                subject="You are Invited! Senior Software Engineer - 03/17/2026",
                body_text="Check out this job that matches your profile.",
                from_address="job-alerts@linkedin.com",
                raw_payload_json="{}",
                extraction_status="pending",
            )
            db.add(msg)
            db.flush()

            # LLM incorrectly returns STATUS/INTERVIEW_REQUEST (misreads "Invited" as interview invite)
            interview_json = json.dumps({
                "category": "STATUS",
                "event_type": "INTERVIEW_REQUEST",
                "company": None,
                "role": "Senior Software Engineer",
                "req_id": None,
                "contacts": [],
                "confidence": 0.85,
                "rationale": "Email invites the candidate to an interview.",
                "jobs": [],
            })
            good_response = LlmResponse(
                raw_text=interview_json,
                prompt_tokens=100,
                completion_tokens=60,
                model="gpt-4o-mini",
            )
            mock_client = MagicMock()
            mock_client.provider_name = "openai"
            mock_client.chat_json.return_value = good_response

            with patch("app.services.extraction.get_llm_client", return_value=mock_client):
                extraction = run_extraction(db, msg.id, tenant.id)

            assert extraction.status == "completed"
            assert extraction.category == "ALERT"
            assert extraction.event_type == "JOB_ALERT"
            assert extraction.alert_jobs_json is not None
            jobs = json.loads(extraction.alert_jobs_json)
            assert len(jobs) == 1
            assert jobs[0].get("role") == "Senior Software Engineer"
            db.refresh(msg)
            assert msg.category == "ALERT"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# build_user_content includes From when provided
# ---------------------------------------------------------------------------

def test_build_user_content_includes_from():
    """build_user_content includes From line when from_address is provided."""
    from app.llm.prompts import build_user_content

    out = build_user_content("Test subject", "Hello world", from_address="noreply@linkedin.com")
    assert "From: noreply@linkedin.com" in out
    assert "Subject: Test subject" in out
    assert "Hello world" in out

    out_no_from = build_user_content("Subj", "Body")
    assert "From: (no from)" in out_no_from


def test_build_user_content_includes_attachment_excerpts():
    from app.llm.prompts import build_user_content

    out = build_user_content(
        "Offer",
        "See attached",
        attachment_texts=[("offer.pdf", "Base salary: $150k")],
    )
    assert "Attachments:" in out
    assert "offer.pdf" in out
    assert "Base salary: $150k" in out
