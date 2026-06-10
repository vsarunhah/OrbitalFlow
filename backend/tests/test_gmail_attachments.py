"""Tests for Gmail inbound attachment parsing."""

import json

from app.providers.gmail import (
    _extract_attachments,
    _parse_message,
    fetch_inline_attachment_bytes,
)


def _fixture_multipart_pdf() -> dict:
    return {
        "id": "msg123",
        "threadId": "thread1",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Offer"},
                {"name": "From", "value": "hr@acme.com"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"size": 20, "data": "SGVsbG8="},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "Offer_Letter.pdf",
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": 'attachment; filename="Offer_Letter.pdf"',
                        },
                        {"name": "Content-Type", "value": "application/pdf"},
                    ],
                    "body": {
                        "attachmentId": "ANGjdJ8pdf",
                        "size": 245760,
                    },
                },
            ],
        },
    }


def test_extract_attachments_from_multipart_mixed():
    payload = _fixture_multipart_pdf()["payload"]
    atts = _extract_attachments(payload)
    assert len(atts) == 1
    assert atts[0].filename == "Offer_Letter.pdf"
    assert atts[0].mime_type == "application/pdf"
    assert atts[0].size_bytes == 245760
    assert atts[0].provider_attachment_id == "ANGjdJ8pdf"


def test_parse_message_includes_attachments():
    raw = _fixture_multipart_pdf()
    fetched = _parse_message(raw)
    assert len(fetched.attachments) == 1
    assert fetched.attachments[0].filename == "Offer_Letter.pdf"
    assert fetched.body_text is not None


def test_extract_attachments_inline_small_part():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Type", "value": "text/plain"}],
                "body": {"size": 5, "data": "aGVsbG8="},
            },
            {
                "mimeType": "text/plain",
                "headers": [
                    {
                        "name": "Content-Disposition",
                        "value": 'attachment; filename="notes.txt"',
                    },
                ],
                "body": {"size": 11, "data": "aGVsbG8gd29ybGQ="},
            },
        ],
    }
    atts = _extract_attachments(payload)
    assert len(atts) == 1
    assert atts[0].filename == "notes.txt"
    assert atts[0].provider_attachment_id is None
    inline = fetch_inline_attachment_bytes(payload, "notes.txt")
    assert inline == b"hello world"


def test_extract_attachments_skips_alternative_body_parts():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"size": 4, "data": "dGVzdA=="},
            },
            {
                "mimeType": "text/html",
                "body": {"size": 10, "data": "PHA+dGVzdDwvcD4="},
            },
        ],
    }
    assert _extract_attachments(payload) == []


def test_extract_attachments_nested_message_rfc822():
    """PDF attached inside a forwarded message/rfc822 part."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "message/rfc822",
                "filename": "Forwarded.eml",
                "parts": [
                    {
                        "mimeType": "multipart/mixed",
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "body": {"size": 4, "data": "dGVzdA=="},
                            },
                            {
                                "mimeType": "application/pdf",
                                "filename": "nested_offer.pdf",
                                "body": {
                                    "attachmentId": "nestedPdfId",
                                    "size": 12000,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }
    atts = _extract_attachments(payload)
    filenames = {a.filename for a in atts}
    assert "nested_offer.pdf" in filenames
    nested = next(a for a in atts if a.filename == "nested_offer.pdf")
    assert nested.provider_attachment_id == "nestedPdfId"
    assert nested.mime_type == "application/pdf"


def test_extract_attachments_inline_image_with_filename():
    payload = {
        "mimeType": "multipart/related",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"size": 10, "data": "PHA+PC9wPg=="},
            },
            {
                "mimeType": "image/png",
                "filename": "logo.png",
                "headers": [
                    {
                        "name": "Content-Disposition",
                        "value": 'inline; filename="logo.png"',
                    },
                ],
                "body": {"attachmentId": "imgAng123", "size": 4096},
            },
        ],
    }
    atts = _extract_attachments(payload)
    assert len(atts) == 1
    assert atts[0].filename == "logo.png"
    assert atts[0].mime_type == "image/png"
    assert atts[0].provider_attachment_id == "imgAng123"
