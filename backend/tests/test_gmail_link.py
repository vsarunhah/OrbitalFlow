"""Tests for Gmail link parsing."""

import pytest

from app.services.gmail_link import parse_gmail_link


class TestParseGmailLink:
    def test_bare_message_id(self):
        parsed = parse_gmail_link("18f3a2b4c5d6e7f8")
        assert parsed.provider_msg_id == "18f3a2b4c5d6e7f8"
        assert parsed.thread_id is None

    def test_hash_all_fragment(self):
        parsed = parse_gmail_link(
            "https://mail.google.com/mail/u/0/#all/18f3a2b4c5d6e7f8"
        )
        assert parsed.provider_msg_id == "18f3a2b4c5d6e7f8"

    def test_hash_inbox_fragment(self):
        parsed = parse_gmail_link(
            "https://mail.google.com/mail/u/0/#inbox/18abc123def456"
        )
        assert parsed.provider_msg_id == "18abc123def456"

    def test_hash_label_fragment(self):
        parsed = parse_gmail_link(
            "https://mail.google.com/mail/u/0/#label/Job%20Search/18abc123def456"
        )
        assert parsed.provider_msg_id == "18abc123def456"

    def test_thread_query_param(self):
        parsed = parse_gmail_link(
            "https://mail.google.com/mail/u/0/?view=om&th=18threadid123456"
        )
        assert parsed.thread_id == "18threadid123456"
        assert parsed.provider_msg_id is None

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            parse_gmail_link("   ")

    def test_unrecognized_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_gmail_link("https://example.com/not-gmail")

    def test_modern_inbox_sync_token_url(self):
        parsed = parse_gmail_link(
            "https://mail.google.com/mail/u/0/#inbox/FMfcgzQgMCZWXZvRrlgcjxRVjfvZlkss"
        )
        assert parsed.thread_id == "19e6ce3fdb64104e"
        assert parsed.provider_msg_id is None

    def test_modern_sync_token_bare(self):
        parsed = parse_gmail_link("FMfcgzQgMCZWXZvRrlgcjxRVjfvZlkss")
        assert parsed.thread_id == "19e6ce3fdb64104e"
