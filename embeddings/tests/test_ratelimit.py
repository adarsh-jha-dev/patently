"""
Tests for the public-deployment request limits.

These guard a cost control, so the failure that matters is the permissive one:
a limiter that quietly allows more than it says drains a shared API quota, and
nothing surfaces until the key stops working.

    cd embeddings && python -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently.ratelimit import DailyBudget, SlidingWindow, client_key


def test_allows_up_to_the_limit_then_blocks():
    w = SlidingWindow(limit=3, window=60)
    assert [w.check("a", now=100)[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = w.check("a", now=100)
    assert allowed is False
    assert 0 < retry_after <= 61


def test_window_slides_rather_than_resetting_on_a_boundary():
    w = SlidingWindow(limit=2, window=60)
    w.check("a", now=100)
    w.check("a", now=130)
    assert w.check("a", now=140)[0] is False
    # The first hit ages out at 160, the second at 190.
    assert w.check("a", now=161)[0] is True
    assert w.check("a", now=162)[0] is False


def test_blocked_requests_do_not_extend_the_block():
    """A client hammering the endpoint must not push its own reset away."""
    w = SlidingWindow(limit=1, window=60)
    w.check("a", now=100)
    for t in range(101, 150):
        w.check("a", now=t)
    assert w.check("a", now=161)[0] is True


def test_clients_are_independent():
    w = SlidingWindow(limit=1, window=60)
    assert w.check("a", now=100)[0] is True
    assert w.check("b", now=100)[0] is True
    assert w.check("a", now=100)[0] is False


def test_key_table_does_not_grow_without_bound():
    """The dict is otherwise a map of every IP ever seen — a slow leak."""
    w = SlidingWindow(limit=1, window=60)
    for i in range(10_050):
        w.check(f"ip-{i}", now=100)
    # Everything is stale by now, so the next call should prune the backlog.
    w.check("fresh", now=100_000)
    assert len(w._hits) < 100


def test_daily_budget_counts_across_all_clients():
    b = DailyBudget(limit=3)
    assert [b.check(now=0)[0] for _ in range(3)] == [True, True, True]
    assert b.check(now=0)[0] is False


def test_daily_budget_rolls_over_at_utc_midnight():
    b = DailyBudget(limit=2)
    b.check(now=0)
    b.check(now=0)
    assert b.check(now=86_399)[0] is False
    assert b.check(now=86_400)[0] is True


def test_budget_reports_remaining():
    b = DailyBudget(limit=3)
    assert b.check(now=0) == (True, 2)
    assert b.check(now=0) == (True, 1)
    assert b.check(now=0) == (True, 0)
    assert b.used == 3


def test_client_key_prefers_the_original_address_behind_a_proxy():
    headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1, 10.0.0.2"}
    assert client_key(headers, "10.0.0.9") == "203.0.113.7"


def test_client_key_falls_back_through_real_ip_then_socket():
    assert client_key({"x-real-ip": "203.0.113.8"}, "10.0.0.9") == "203.0.113.8"
    assert client_key({}, "10.0.0.9") == "10.0.0.9"
    # An empty forwarded header must not become an empty key shared by everyone.
    assert client_key({"x-forwarded-for": ""}, "10.0.0.9") == "10.0.0.9"
