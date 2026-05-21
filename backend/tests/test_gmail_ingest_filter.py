"""Tests for Gmail ingest label filtering."""

from app.providers.gmail import should_skip_ingest


def test_should_skip_ingest_draft():
    assert should_skip_ingest(["DRAFT"]) is True


def test_should_skip_ingest_spam_and_trash():
    assert should_skip_ingest(["SPAM"]) is True
    assert should_skip_ingest(["TRASH"]) is True


def test_should_skip_ingest_inbox_and_sent():
    assert should_skip_ingest(["INBOX", "UNREAD"]) is False
    assert should_skip_ingest(["SENT"]) is False


def test_should_skip_ingest_empty_or_none():
    assert should_skip_ingest(None) is False
    assert should_skip_ingest([]) is False
