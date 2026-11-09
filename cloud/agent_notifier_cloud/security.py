"""Hashing, CSRF and rate limiting helpers."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

PAT_PREFIX = "an_pat_"
_SAFE_NEXT = re.compile(r"^/[A-Za-z0-9_\-./?=&%]*$")


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def csrf_token(secret: str, sid: str) -> str:
    return hmac.new(secret.encode(), b"csrf:" + sid.encode(), hashlib.sha256).hexdigest()[:40]


def csrf_ok(secret: str, sid: str, given: str) -> bool:
    return bool(sid and given) and hmac.compare_digest(csrf_token(secret, sid), given)


def safe_next(value: str | None) -> str:
    """Only allow same-site relative paths (blocks open redirects)."""
    if value and value.startswith("/") and not value.startswith("//") and _SAFE_NEXT.match(value):
        return value
    return "/app"


class RateLimiter:
    """In-memory sliding window; fine for a single process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(self._hits) > 20000:  # crude memory bound
            self._hits.clear()
        return True
