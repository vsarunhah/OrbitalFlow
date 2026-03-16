"""Tests for Phase 7: Gmail labeling service.

All Gmail API calls are mocked via httpx. Covers:
- ensure_label: returns existing label or creates new
- apply_label: idempotent label application
- label_message_if_configured: full integration with tenant settings
- Tenant settings API endpoints
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.encryption import encrypt
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.message_extraction import MessageExtraction
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.services.gmail_labeling import (
    apply_label,
    ensure_label,
    get_or_create_tenant_settings,
    label_message_if_configured,
)


# --------------- fixtures ---------------

@pytest.fixture()
def db():
    """Provide a test DB session."""
    from tests.conftest import TestSession
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def tenant(db):
    t = Tenant(name="TestCo")
    db.add(t)
    db.commit()
    return t


@pytest.fixture()
def email_account(db, tenant):
    oauth_blob = encrypt(json.dumps({
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
    }))
    acct = EmailAccount(
        tenant_id=tenant.id,
        email_address="user@example.com",
        provider="gmail",
        oauth_encrypted=oauth_blob,
    )
    db.add(acct)
    db.commit()
    return acct


@pytest.fixture()
def message(db, tenant, email_account):
    msg = Message(
        tenant_id=tenant.id,
        account_id=email_account.id,
        provider_msg_id="gmail_msg_123",
        thread_id="thread_abc",
        subject="Your application status",
        raw_payload_json="{}",
        extraction_status="completed",
    )
    db.add(msg)
    db.commit()
    return msg


@pytest.fixture()
def extraction(db, tenant, message):
    ext = MessageExtraction(
        tenant_id=tenant.id,
        message_id=message.id,
        category="STATUS",
        event_type="APPLICATION_RECEIVED",
        confidence=0.92,
        status="completed",
    )
    db.add(ext)
    db.commit()
    return ext


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# --------------- ensure_label tests ---------------


class TestEnsureLabel:
    @patch("app.services.gmail_labeling.httpx.get")
    def test_returns_existing_label_id(self, mock_get):
        mock_get.return_value = _mock_response(json_data={
            "labels": [
                {"id": "Label_1", "name": "JobTracker/Status"},
                {"id": "Label_2", "name": "INBOX"},
            ]
        })

        label_id = ensure_label("tok", "JobTracker/Status")

        assert label_id == "Label_1"
        mock_get.assert_called_once()

    @patch("app.services.gmail_labeling.httpx.post")
    @patch("app.services.gmail_labeling.httpx.get")
    def test_creates_label_when_missing(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(json_data={
            "labels": [{"id": "Label_2", "name": "INBOX"}]
        })
        mock_post.return_value = _mock_response(json_data={
            "id": "Label_new",
            "name": "JobTracker/Status",
        })

        label_id = ensure_label("tok", "JobTracker/Status")

        assert label_id == "Label_new"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["json"]["name"] == "JobTracker/Status"

    @patch("app.services.gmail_labeling.httpx.get")
    def test_does_not_create_duplicate(self, mock_get):
        """If label already exists, no POST is made."""
        mock_get.return_value = _mock_response(json_data={
            "labels": [{"id": "Label_99", "name": "JobTracker/Recruiter"}]
        })

        label_id = ensure_label("tok", "JobTracker/Recruiter")
        assert label_id == "Label_99"


# --------------- apply_label tests ---------------


class TestApplyLabel:
    @patch("app.services.gmail_labeling.httpx.post")
    def test_apply_label_calls_modify(self, mock_post):
        mock_post.return_value = _mock_response(json_data={"id": "msg1"})

        apply_label("tok", "msg1", "Label_1")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "msg1/modify" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"] == {"addLabelIds": ["Label_1"]}

    @patch("app.services.gmail_labeling.httpx.post")
    def test_apply_label_idempotent(self, mock_post):
        """Calling twice should issue two API calls but not error."""
        mock_post.return_value = _mock_response(json_data={"id": "msg1"})

        apply_label("tok", "msg1", "Label_1")
        apply_label("tok", "msg1", "Label_1")

        assert mock_post.call_count == 2


# --------------- get_or_create_tenant_settings tests ---------------


class TestTenantSettings:
    def test_creates_defaults(self, db, tenant):
        settings = get_or_create_tenant_settings(db, tenant.id)
        db.commit()

        assert settings.labeling_enabled is False
        assert settings.labeling_confidence_threshold == 0.75
        assert settings.label_status == "JobTracker/Status"
        assert settings.label_recruiter == "JobTracker/Recruiter"
        assert settings.label_alerts == "JobTracker/Alerts"

    def test_returns_existing(self, db, tenant):
        existing = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.90,
        )
        db.add(existing)
        db.commit()

        result = get_or_create_tenant_settings(db, tenant.id)
        assert result.id == existing.id
        assert result.labeling_enabled is True
        assert result.labeling_confidence_threshold == 0.90


# --------------- label_message_if_configured tests ---------------


class TestLabelMessageIfConfigured:
    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", return_value="Label_1")
    @patch("app.services.gmail_labeling.apply_label")
    def test_labels_when_enabled_and_above_threshold(
        self, mock_apply, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.80,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)

        assert result is True
        mock_ensure.assert_called_once_with("tok", "JobTracker/Status")
        mock_apply.assert_called_once_with("tok", "gmail_msg_123", "Label_1")

    def test_skips_when_disabled(
        self, db, tenant, email_account, message, extraction,
    ):
        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=False,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False

    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", return_value="Label_1")
    @patch("app.services.gmail_labeling.apply_label")
    def test_skips_when_below_threshold(
        self, mock_apply, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.95,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False
        mock_apply.assert_not_called()

    def test_skips_other_category(
        self, db, tenant, email_account, message, extraction,
    ):
        extraction.category = "OTHER"
        db.commit()

        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.50,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False

    def test_skips_failed_extraction(
        self, db, tenant, email_account, message, extraction,
    ):
        extraction.status = "failed"
        db.commit()

        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False

    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", return_value="Label_R")
    @patch("app.services.gmail_labeling.apply_label")
    def test_recruiter_category_uses_recruiter_label(
        self, mock_apply, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        extraction.category = "RECRUITER"
        db.commit()

        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.50,
            label_recruiter="MyCustom/Recruiter",
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is True
        mock_ensure.assert_called_once_with("tok", "MyCustom/Recruiter")

    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", return_value="Label_A")
    @patch("app.services.gmail_labeling.apply_label")
    def test_alert_category_uses_alerts_label(
        self, mock_apply, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        extraction.category = "ALERT"
        db.commit()

        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.50,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is True
        mock_ensure.assert_called_once_with("tok", "JobTracker/Alerts")

    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", side_effect=Exception("API down"))
    def test_handles_gmail_api_failure_gracefully(
        self, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        settings = TenantSettings(
            tenant_id=tenant.id,
            labeling_enabled=True,
            labeling_confidence_threshold=0.50,
        )
        db.add(settings)
        db.commit()

        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False

    @patch("app.services.gmail_labeling._ensure_valid_token", return_value="tok")
    @patch("app.services.gmail_labeling.ensure_label", return_value="Label_1")
    @patch("app.services.gmail_labeling.apply_label")
    def test_creates_default_settings_when_none_exist(
        self, mock_apply, mock_ensure, mock_token,
        db, tenant, email_account, message, extraction,
    ):
        """When no TenantSettings row exists, defaults are created (labeling_enabled=False)."""
        result = label_message_if_configured(db, email_account, message, extraction)
        assert result is False
        mock_apply.assert_not_called()

        settings = db.query(TenantSettings).filter(
            TenantSettings.tenant_id == tenant.id
        ).first()
        assert settings is not None
        assert settings.labeling_enabled is False


# --------------- Tenant settings API tests ---------------


class TestTenantSettingsAPI:
    def test_get_returns_defaults(self, client, auth_header):
        resp = client.get("/settings", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["labeling_enabled"] is False
        assert data["labeling_confidence_threshold"] == 0.75
        assert data["label_status"] == "JobTracker/Status"
        assert data["label_recruiter"] == "JobTracker/Recruiter"
        assert data["label_alerts"] == "JobTracker/Alerts"

    def test_patch_updates_fields(self, client, auth_header):
        resp = client.patch("/settings", headers=auth_header, json={
            "labeling_enabled": True,
            "labeling_confidence_threshold": 0.85,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["labeling_enabled"] is True
        assert data["labeling_confidence_threshold"] == 0.85
        assert data["label_status"] == "JobTracker/Status"

    def test_patch_custom_labels(self, client, auth_header):
        resp = client.patch("/settings", headers=auth_header, json={
            "label_status": "Custom/StatusLabel",
            "label_recruiter": "Custom/RecruiterLabel",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["label_status"] == "Custom/StatusLabel"
        assert data["label_recruiter"] == "Custom/RecruiterLabel"
        assert data["label_alerts"] == "JobTracker/Alerts"

    def test_patch_validates_threshold(self, client, auth_header):
        resp = client.patch("/settings", headers=auth_header, json={
            "labeling_confidence_threshold": 1.5,
        })
        assert resp.status_code == 422

    def test_get_requires_auth(self, client):
        resp = client.get("/settings")
        assert resp.status_code in (401, 403)

    def test_settings_are_persistent(self, client, auth_header):
        client.patch("/settings", headers=auth_header, json={
            "labeling_enabled": True,
        })
        resp = client.get("/settings", headers=auth_header)
        assert resp.json()["labeling_enabled"] is True
