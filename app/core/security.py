"""JWT and password hashing helpers.

Access tokens are short-lived HS256 JWTs. Refresh tokens are opaque
URL-safe random values whose bcrypt hash is persisted server-side and
rotated on every use (see :mod:`app.services.user_service`).
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

REFRESH_TOKEN_BYTES = 32


class TokenError(Exception):
    """Raised when a token cannot be decoded or is otherwise invalid."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    sub: str
    role: str
    jti: str
    exp: datetime
    iat: datetime


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    settings: Settings,
    *,
    subject: uuid.UUID,
    role: str,
) -> tuple[str, AccessTokenClaims]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, AccessTokenClaims(
        sub=str(subject), role=role, jti=jti, exp=expires, iat=now
    )


def decode_access_token(settings: Settings, token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise TokenError("invalid access token") from exc

    try:
        return AccessTokenClaims(
            sub=str(payload["sub"]),
            role=str(payload["role"]),
            jti=str(payload["jti"]),
            exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            iat=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("malformed access token claims") from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return _pwd_context.hash(token)


def verify_refresh_token(token: str, hashed: str) -> bool:
    return _pwd_context.verify(token, hashed)
