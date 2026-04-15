"""In-memory sliding-window rate limiter for the login endpoint.

This is deliberately small and process-local. The production deployment
runs a single Gunicorn instance behind Nginx; if that ever changes, swap
this module for a Redis-backed limiter without touching call sites.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class _Bucket:
    hits: deque[float] = field(default_factory=deque)


class SlidingWindowRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        if max_attempts <= 0 or window_seconds <= 0:
            raise ValueError("max_attempts and window_seconds must be positive")
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check_and_record(self, key: str) -> bool:
        """Record a hit for ``key`` and return True if it is allowed."""

        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket())
            while bucket.hits and bucket.hits[0] < cutoff:
                bucket.hits.popleft()
            if len(bucket.hits) >= self._max_attempts:
                return False
            bucket.hits.append(now)
            return True

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._buckets.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._buckets.clear()
