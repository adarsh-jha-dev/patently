"""
Request limits for the public deployment.

The concern is cost, not security. `/analyze` spends two LLM calls per request
against a single shared API key, so an unthrottled public endpoint is one `for`
loop away from an exhausted quota or a real bill. Two independent limits:

  per-client   a sliding window keyed on IP, so one visitor cannot monopolise
  daily budget an absolute ceiling on analyses per day across everyone

The daily budget matters more than the per-IP window. A window alone still
lets a hundred distinct clients drain the quota; the budget is the number that
actually bounds the spend.

State is in-memory, so limits are per-process and reset on redeploy. That is
the right trade for a single-container demo — a shared store would mean
another dependency to provision and keep alive. If this ever runs more than
one replica, the effective limit multiplies by the replica count, which is
worth remembering before scaling out.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


# 5 analyses per hour per IP is generous for someone exploring a demo and
# useless for someone scripting against it.
RATE_LIMIT = _int_env("PATENTLY_RATE_LIMIT", 5)
RATE_WINDOW = _int_env("PATENTLY_RATE_WINDOW", 3600)
DAILY_BUDGET = _int_env("PATENTLY_DAILY_BUDGET", 200)


class SlidingWindow:
    """Allow `limit` events per `window` seconds, per key."""

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds).

        Recording happens only on success, so a client that is already blocked
        does not push its own reset further away with every rejected retry.
        """
        now = time.time() if now is None else now
        cutoff = now - self.window
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                return False, max(1, int(hits[0] + self.window - now) + 1)

            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(cutoff)
            return True, 0

    def _prune(self, cutoff: float) -> None:
        """Drop keys with no live hits. Called under the lock.

        Without this the dict is an unbounded map of every IP ever seen — a
        slow leak that only shows up after the demo has been up for a while.
        """
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class DailyBudget:
    """A hard ceiling on how many analyses run per UTC day, across all clients."""

    def __init__(self, limit: int):
        self.limit = limit
        self._day: int | None = None
        self._used = 0
        self._lock = threading.Lock()

    def check(self, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, remaining_after_this_one)."""
        now = time.time() if now is None else now
        day = int(now // 86400)
        with self._lock:
            if day != self._day:
                self._day, self._used = day, 0
            if self._used >= self.limit:
                return False, 0
            self._used += 1
            return True, self.limit - self._used

    @property
    def used(self) -> int:
        return self._used

    def reset(self) -> None:
        with self._lock:
            self._day, self._used = None, 0


def client_key(headers, fallback: str) -> str:
    """
    Identify the caller behind a proxy.

    Every platform this deploys to (Spaces, Cloud Run, Fly) terminates TLS
    upstream, so request.client.host is the proxy and useless as a key. The
    original address is the first entry of X-Forwarded-For. This is spoofable
    by a determined caller — the daily budget is what actually bounds spend.
    """
    forwarded = headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return headers.get("x-real-ip") or fallback


analyses = SlidingWindow(RATE_LIMIT, RATE_WINDOW)
budget = DailyBudget(DAILY_BUDGET)
