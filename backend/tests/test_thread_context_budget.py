"""Tests for full-thread body budget allocation."""

from __future__ import annotations

from app.services.thread_context_builder import (
    THREAD_TOTAL_BODY_BUDGET_CHARS,
    _allocate_message_bodies,
)


def test_allocate_keeps_all_short_bodies():
    bodies = ["a" * 100, "b" * 200, "c" * 300]
    out = _allocate_message_bodies(bodies)
    assert out[0] == bodies[0]
    assert out[2] == bodies[2]


def test_allocate_truncates_when_over_budget():
    bodies = ["x" * 20_000, "y" * 20_000]
    out = _allocate_message_bodies(bodies)
    assert sum(len(b) for b in out) <= THREAD_TOTAL_BODY_BUDGET_CHARS + 50
    assert "[...truncated...]" in out[0] or "[...truncated...]" in out[1]
    # Newer message should retain more content when forced to trim
    assert len(out[1]) >= len(out[0])
