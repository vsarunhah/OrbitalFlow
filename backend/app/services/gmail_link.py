"""Parse Gmail web URLs into message or thread identifiers."""

from __future__ import annotations

import re
from base64 import b64decode
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

# Legacy hex ids accepted by Gmail API (messages.list / threads.get).
_API_HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{15,16}$")
# Modern Gmail web UI "sync" tokens (address bar), not valid API ids directly.
_SYNC_TOKEN_RE = re.compile(r"^FMfcgz[A-Za-z0-9_-]{20,}$")
# Test / opaque provider ids (non-sync) still accepted for direct API fetch attempts.
_LEGACY_PROVIDER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")
_CHARSET_FULL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_CHARSET_REDUCED = "BCDFGHJKLMNPQRSTVWXZbcdfghjklmnpqrstvwxz"


@dataclass(frozen=True)
class ParsedGmailLink:
    """Result of parsing a Gmail URL or bare provider id."""

    provider_msg_id: str | None = None
    thread_id: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_msg_id and not self.thread_id:
            raise ValueError("ParsedGmailLink requires provider_msg_id or thread_id")


def parse_gmail_link(raw: str) -> ParsedGmailLink:
    """Extract a Gmail API message/thread id from a URL, sync token, or bare hex id."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Email link is required")

    if "://" not in text and "/" not in text:
        return _resolve_token(text)

    parsed = urlparse(text)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError("Unsupported URL scheme; use a Gmail link or message id")

    query = parse_qs(parsed.query)
    th_values = query.get("th") or query.get("thread")
    if th_values:
        thread_token = th_values[0].strip()
        if thread_token:
            if _SYNC_TOKEN_RE.fullmatch(thread_token):
                return _parsed_from_sync_token(thread_token)
            return ParsedGmailLink(thread_id=thread_token)

    fragment = (parsed.fragment or "").strip()
    if fragment:
        # #all/MSG, #inbox/MSG, #label/Name/MSG, #search/query/MSG
        parts = [p for p in fragment.split("/") if p]
        if parts:
            candidate = parts[-1].strip()
            if candidate:
                return _resolve_token(candidate)

    raise ValueError(
        "Could not parse Gmail link. Paste a link like "
        "https://mail.google.com/mail/u/0/#inbox/<id>"
    )


def _resolve_token(token: str) -> ParsedGmailLink:
    if _SYNC_TOKEN_RE.fullmatch(token):
        return _parsed_from_sync_token(token)
    if _API_HEX_ID_RE.fullmatch(token):
        return ParsedGmailLink(provider_msg_id=token)
    if _LEGACY_PROVIDER_ID_RE.fullmatch(token):
        return ParsedGmailLink(provider_msg_id=token)

    raise ValueError(
        "Could not parse Gmail link. Paste a full Gmail URL from the address bar "
        "(#inbox/… or #all/…) for an email in your connected inbox."
    )


def _parsed_from_sync_token(token: str) -> ParsedGmailLink:
    """Decode modern Gmail web sync token (FMfcgz…) to an API thread/message id."""
    decoded = _decode_sync_token(token)
    if not decoded:
        raise ValueError(
            "Could not decode this Gmail link. Open the email in Gmail and copy the "
            "full URL from the address bar, then try again."
        )

    if decoded.startswith("thread-f:"):
        api_id = _sync_timestamp_to_hex(decoded.split(":", 1)[1])
        return ParsedGmailLink(thread_id=api_id)

    if decoded.startswith("msg-f:"):
        api_id = _sync_timestamp_to_hex(decoded.split(":", 1)[1])
        return ParsedGmailLink(provider_msg_id=api_id)

    raise ValueError(
        "This Gmail link uses a format we cannot resolve automatically. "
        "Try opening the email in Gmail, press ⋮ → 'Forward as attachment' is not needed — "
        "instead copy the link after the email fully loads, or use an older hex id link if available."
    )


def _sync_timestamp_to_hex(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 15:
        raise ValueError("Decoded Gmail sync token is missing a timestamp")
    # Gmail encodes a nanosecond-scale timestamp; 15–19 digits are typical.
    value = int(digits[:19])
    return format(value, "x")


def _decode_sync_token(token: str) -> str | None:
    """Decode FMfcgz web sync token (see GmailURLDecoder / danrouse gist)."""
    try:
        out_str = _transform_charset(token, _CHARSET_REDUCED, _CHARSET_FULL)
        padding = "=" * (-len(out_str) % 4)
        result = b64decode(out_str + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if not result.startswith("thread-") and not result.startswith("msg-"):
        result = f"thread-{result}"
    return result


def _transform_charset(token: str, charset_in: str, charset_out: str) -> str:
    size_in = len(charset_in)
    size_out = len(charset_out)
    alph_map = {charset_in[i]: i for i in range(size_in)}
    in_str_idx = [alph_map[token[i]] for i in reversed(range(len(token)))]
    out_str_idx: list[int] = []

    for i in reversed(range(len(in_str_idx))):
        offset = 0
        for j in range(len(out_str_idx)):
            idx = size_in * out_str_idx[j] + offset
            if idx >= size_out:
                rest = idx % size_out
                offset = (idx - rest) // size_out
                idx = rest
            else:
                offset = 0
            out_str_idx[j] = idx
        while offset:
            rest = offset % size_out
            out_str_idx.append(rest)
            offset = (offset - rest) // size_out
        offset = in_str_idx[i]
        j = 0
        while offset:
            if j >= len(out_str_idx):
                out_str_idx.append(0)
            idx = out_str_idx[j] + offset
            if idx >= size_out:
                rest = idx % size_out
                offset = (idx - rest) // size_out
                idx = rest
            else:
                offset = 0
            out_str_idx[j] = idx
            j += 1

    return "".join(charset_out[out_str_idx[i]] for i in reversed(range(len(out_str_idx))))
