"""Config validation rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _base_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "app_env": "test",
        "database_url": "postgresql+asyncpg://u:p@h/db",
        "jwt_secret": "a" * 48,
        "storage_dir": tmp_path,
    }


def test_rejects_short_jwt_secret(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["jwt_secret"] = "short"
    with pytest.raises(ValidationError):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_accepts_long_jwt_secret(tmp_path: Path) -> None:
    settings = Settings(**_base_kwargs(tmp_path))  # type: ignore[arg-type]
    assert len(settings.jwt_secret) >= 32


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("https://a.example.com", ["https://a.example.com"]),
        (
            "https://a.example.com, https://b.example.com ",
            ["https://a.example.com", "https://b.example.com"],
        ),
    ],
)
def test_cors_origins_parsing(
    tmp_path: Path, raw: str, expected: list[str]
) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["cors_allowed_origins"] = raw
    settings = Settings(**kwargs)  # type: ignore[arg-type]
    assert settings.cors_origins == expected
