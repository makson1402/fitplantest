"""In-memory sliding-window rate limiter for the auth routes (B-02).

Single backend instance, so process memory is enough. Behind a reverse proxy run uvicorn with
`--proxy-headers` so that `request.client.host` is the real client address.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.errors import AppError


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> float | None:
        """Record one request. Return None if allowed, otherwise seconds until the next request is allowed."""
        now = self.clock()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


async def auth_rate_limit(request: Request) -> None:
    """FastAPI dependency: limit per (route, client IP)."""
    limiter: RateLimiter = request.app.state.auth_rate_limiter
    client = request.client.host if request.client else "unknown"
    retry_after = limiter.hit(f"{request.url.path}|{client}")
    if retry_after is not None:
        raise AppError(429, "rate_limited", "Too many requests, try again later",
                       headers={"Retry-After": str(max(1, math.ceil(retry_after)))})
