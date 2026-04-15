"""Sliding window rate limiter behaviour."""

from __future__ import annotations

import asyncio

import pytest

from app.core.rate_limit import SlidingWindowRateLimiter


async def test_allows_up_to_max_attempts() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert await limiter.check_and_record("a")
    assert await limiter.check_and_record("a")
    assert await limiter.check_and_record("a")
    assert not await limiter.check_and_record("a")


async def test_isolates_keys() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert await limiter.check_and_record("a")
    assert await limiter.check_and_record("b")
    assert not await limiter.check_and_record("a")


async def test_reset_clears_bucket() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    await limiter.check_and_record("a")
    await limiter.reset("a")
    assert await limiter.check_and_record("a")


@pytest.mark.parametrize("max_attempts,window", [(0, 1), (1, 0), (-1, 5)])
async def test_invalid_config_raises(max_attempts: int, window: int) -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(
            max_attempts=max_attempts, window_seconds=window
        )


async def test_concurrent_check_and_record_is_thread_safe() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=60)
    results = await asyncio.gather(
        *(limiter.check_and_record("a") for _ in range(10))
    )
    assert sum(1 for r in results if r) == 5
