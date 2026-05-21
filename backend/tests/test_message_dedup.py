"""Tests for message ingestion idempotency.

Verifies that the unique(account_id, provider_msg_id) constraint prevents
duplicate messages, and that the process_message job handles duplicates
gracefully.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from cryptography.fernet import Fernet

from app.config import settings

settings.app_encryption_key = Fernet.generate_key().decode()

from app.database import Base  # noqa: E402
from app.encryption import reset_fernet  # noqa: E402
from app.models.email_account import EmailAccount  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.providers.base import FetchedMessage  # noqa: E402

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def setup_db():
    reset_fernet()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def tenant_and_account(db):
    """Create a tenant + email account for testing."""
    from app.encryption import encrypt

    tenant = Tenant(id=uuid.uuid4(), name="TestCo")
    db.add(tenant)
    db.flush()

    oauth_blob = json.dumps({
        "access_token": "fake-access",
        "refresh_token": "fake-refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
    })
    account = EmailAccount(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email_address="test@example.com",
        provider="gmail",
        oauth_encrypted=encrypt(oauth_blob),
        sync_cursor_json='{"history_id": null, "last_polled_at": null}',
        status="active",
    )
    db.add(account)
    db.commit()
    return tenant, account


def _make_message(db, account, provider_msg_id="msg_001"):
    """Insert a message row directly."""
    msg = Message(
        tenant_id=account.tenant_id,
        account_id=account.id,
        provider_msg_id=provider_msg_id,
        thread_id="thread_001",
        subject="Test email",
        from_address="sender@example.com",
        to_addresses="recipient@example.com",
        date_header=datetime.now(timezone.utc),
        body_text="Hello world",
        body_html="<p>Hello world</p>",
        headers_json="{}",
        raw_payload_json="{}",
        label_ids_json=None,
        extraction_status="pending",
    )
    db.add(msg)
    db.commit()
    return msg


class TestMessageDedupModel:
    """Test the DB-level unique constraint on (account_id, provider_msg_id)."""

    def test_insert_same_provider_msg_id_raises_integrity_error(
        self, db, tenant_and_account
    ):
        _, account = tenant_and_account
        _make_message(db, account, provider_msg_id="msg_dup")

        dup = Message(
            tenant_id=account.tenant_id,
            account_id=account.id,
            provider_msg_id="msg_dup",
            thread_id="thread_002",
            subject="Duplicate",
            from_address="other@example.com",
            raw_payload_json="{}",
            headers_json="{}",
            extraction_status="pending",
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_different_provider_msg_id_succeeds(self, db, tenant_and_account):
        _, account = tenant_and_account
        _make_message(db, account, provider_msg_id="msg_A")
        _make_message(db, account, provider_msg_id="msg_B")

        count = db.query(Message).filter(Message.account_id == account.id).count()
        assert count == 2

    def test_same_provider_msg_id_different_account_succeeds(self, db, tenant_and_account):
        tenant, account1 = tenant_and_account
        _make_message(db, account1, provider_msg_id="msg_shared")

        from app.encryption import encrypt

        account2 = EmailAccount(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email_address="other@example.com",
            provider="gmail",
            oauth_encrypted=encrypt(json.dumps({"access_token": "x"})),
            sync_cursor_json="{}",
            status="active",
        )
        db.add(account2)
        db.commit()

        _make_message(db, account2, provider_msg_id="msg_shared")
        total = db.query(Message).filter(
            Message.provider_msg_id == "msg_shared"
        ).count()
        assert total == 2


class TestProcessMessageDedup:
    """Test that the process_message job handles duplicates gracefully."""

    def _fake_fetched(self, provider_msg_id="msg_rq_001"):
        return FetchedMessage(
            provider_msg_id=provider_msg_id,
            thread_id="thread_rq",
            subject="RQ test",
            from_address="rq@example.com",
            to_addresses="me@example.com",
            date_header=datetime.now(timezone.utc).isoformat(),
            body_text="body",
            body_html="<p>body</p>",
            headers_json="{}",
            raw_payload_json="{}",
            label_ids_json=None,
        )

    @patch("app.workers.jobs.SessionLocal")
    @patch("app.workers.jobs.GmailProvider")
    def test_process_message_skips_existing(
        self, mock_provider_cls, mock_session_cls, db, tenant_and_account
    ):
        _, account = tenant_and_account
        _make_message(db, account, provider_msg_id="msg_exists")

        mock_session_cls.return_value = db
        from app.workers.jobs import process_message

        result = process_message(str(account.id), "msg_exists")
        assert result["status"] == "skipped"
        assert result["reason"] == "duplicate"
        mock_provider_cls.assert_not_called()

    @patch("app.workers.jobs.SessionLocal")
    @patch("app.workers.jobs.GmailProvider")
    def test_process_message_stores_new(
        self, mock_provider_cls, mock_session_cls, db, tenant_and_account
    ):
        _, account = tenant_and_account
        fetched = self._fake_fetched("msg_new_001")
        mock_provider_cls.return_value.fetch_message.return_value = fetched
        mock_session_cls.return_value = db

        from app.workers.jobs import process_message

        result = process_message(str(account.id), "msg_new_001")
        assert result["status"] == "ok"

        msg = db.query(Message).filter(
            Message.provider_msg_id == "msg_new_001"
        ).first()
        assert msg is not None
        assert msg.account_id == account.id
        assert msg.subject == "RQ test"
        assert msg.extraction_status in ("pending", "extraction_failed")

    @patch("app.workers.jobs.SessionLocal")
    @patch("app.workers.jobs.GmailProvider")
    def test_process_message_twice_second_is_skipped(
        self, mock_provider_cls, mock_session_cls, db, tenant_and_account
    ):
        """Simulate processing the same message twice; second call should skip."""
        _, account = tenant_and_account
        fetched = self._fake_fetched("msg_twice")
        mock_provider_cls.return_value.fetch_message.return_value = fetched
        mock_session_cls.return_value = db

        from app.workers.jobs import process_message

        result1 = process_message(str(account.id), "msg_twice")
        assert result1["status"] == "ok"

        result2 = process_message(str(account.id), "msg_twice")
        assert result2["status"] == "skipped"
        assert result2["reason"] == "duplicate"

        count = db.query(Message).filter(
            Message.provider_msg_id == "msg_twice",
            Message.account_id == account.id,
        ).count()
        assert count == 1

    @patch("app.workers.jobs.SessionLocal")
    @patch("app.workers.jobs.GmailProvider")
    def test_process_message_skips_draft_label(
        self, mock_provider_cls, mock_session_cls, db, tenant_and_account
    ):
        _, account = tenant_and_account
        fetched = self._fake_fetched("msg_draft_001")
        fetched = FetchedMessage(
            provider_msg_id=fetched.provider_msg_id,
            thread_id=fetched.thread_id,
            subject=fetched.subject,
            from_address=fetched.from_address,
            to_addresses=fetched.to_addresses,
            date_header=fetched.date_header,
            body_text=fetched.body_text,
            body_html=fetched.body_html,
            headers_json=fetched.headers_json,
            raw_payload_json=fetched.raw_payload_json,
            label_ids_json=json.dumps(["DRAFT"]),
        )
        mock_provider_cls.return_value.fetch_message.return_value = fetched
        mock_session_cls.return_value = db

        from app.workers.jobs import process_message

        result = process_message(str(account.id), "msg_draft_001")
        assert result["status"] == "skipped"
        assert result["reason"] == "excluded_labels"

        assert (
            db.query(Message)
            .filter(Message.provider_msg_id == "msg_draft_001")
            .first()
            is None
        )
