"""JWT and password hashing round trips."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)


def test_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password at all", hashed)


def test_access_token_round_trip(test_settings: Settings) -> None:
    subject = uuid.uuid4()
    token, claims = create_access_token(
        test_settings, subject=subject, role="user"
    )
    decoded = decode_access_token(test_settings, token)
    assert decoded.sub == str(subject)
    assert decoded.role == "user"
    assert decoded.jti == claims.jti
    assert decoded.exp > datetime.now(UTC)


def test_access_token_rejects_garbage(test_settings: Settings) -> None:
    with pytest.raises(TokenError):
        decode_access_token(test_settings, "not-a-jwt")


def test_access_token_expiration_window(test_settings: Settings) -> None:
    _, claims = create_access_token(
        test_settings, subject=uuid.uuid4(), role="admin"
    )
    expected_expiry = claims.iat + timedelta(
        minutes=test_settings.access_token_ttl_minutes
    )
    assert abs((claims.exp - expected_expiry).total_seconds()) < 2


def test_refresh_token_round_trip() -> None:
    token = generate_refresh_token()
    assert len(token) >= 32
    hashed = hash_refresh_token(token)
    assert verify_refresh_token(token, hashed)
    assert not verify_refresh_token(token + "x", hashed)
