"""Sliding window rate limiter behaviour."""

from __future__ import annotations

import asyncio

import pytest

from app.core.rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_allows_up_to_limit() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert await limiter.check_and_record("k") is True
    assert await limiter.check_and_record("k") is True
    assert await limiter.check_and_record("k") is True
    assert await limiter.check_and_record("k") is False


@pytest.mark.asyncio
async def test_buckets_are_per_key() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert await limiter.check_and_record("a") is True
    assert await limiter.check_and_record("b") is True
    assert await limiter.check_and_record("a") is False


@pytest.mark.asyncio
async def test_reset_clears_a_bucket() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert await limiter.check_and_record("k") is True
    assert await limiter.check_and_record("k") is False
    await limiter.reset("k")
    assert await limiter.check_and_record("k") is True


def test_invalid_construction_rejected() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(max_attempts=0, window_seconds=60)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(max_attempts=1, window_seconds=0)


@pytest.mark.asyncio
async def test_clear_empties_all_buckets() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=60)
    await asyncio.gather(*(limiter.check_and_record(f"k{i}") for i in range(5)))
    await limiter.clear()
    for i in range(5):
        assert await limiter.check_and_record(f"k{i}") is True
