"""Tests for Gmail polling provider (lookback / after query formatting)."""

from datetime import datetime, timezone

import pytest

from app.providers.polling import _after_query_from_epoch


def test_after_query_from_epoch_uses_gmail_date_format():
    """Gmail API expects after:YYYY/MM/DD; epoch seconds were not honored."""
    # 2024-01-15 00:00:00 UTC
    epoch = 1705276800
    assert _after_query_from_epoch(epoch) == "2024/01/15"


def test_after_query_from_epoch_midday():
    """Date is in UTC; time-of-day does not change the calendar day in query."""
    # 2024-06-10 12:30:00 UTC
    epoch = 1718015400
    assert _after_query_from_epoch(epoch) == "2024/06/10"


def test_after_query_from_epoch_year_boundary():
    """Year boundary is formatted correctly."""
    # 2023-12-31 23:59:59 UTC
    dt = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert _after_query_from_epoch(int(dt.timestamp())) == "2023/12/31"
