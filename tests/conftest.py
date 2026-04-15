"""Shared pytest fixtures."""

from __future__ import annotations

import base64
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.core.config import Settings


@pytest.fixture
def storage_tmpdir(tmp_path: Path) -> Path:
    directory = tmp_path / "softtarget"
    directory.mkdir()
    return directory


@pytest.fixture
def test_settings(storage_tmpdir: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://test:test@localhost:5432/softtarget_test",
        jwt_secret=base64.b64encode(secrets.token_bytes(48)).decode(),
        storage_dir=storage_tmpdir,
        cors_allowed_origins="http://localhost:3000",
        enable_docs=True,
    )


@pytest.fixture
async def async_client() -> AsyncIterator[object]:
    """Placeholder — integration tests override this with a real app client."""

    raise NotImplementedError(
        "async_client is only available in integration tests that spin up "
        "a real Postgres via docker-compose.test.yml"
    )
    yield  # pragma: no cover
