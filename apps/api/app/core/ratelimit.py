"""Small in-memory sliding-window limiter for unauthenticated routes.

Good enough for a single Railway/Fly instance; swap for Redis if you scale horizontally.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import ApiError


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 3600) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry_after = int(self.window - (now - q[0])) + 1
            raise ApiError(
                429, "rate_limited", "Too many requests; try again later.", retry_after_seconds=retry_after
            )
        q.append(now)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
