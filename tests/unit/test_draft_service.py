"""DraftService behaviour."""

from __future__ import annotations

from typing import Any

import pytest

from app.models.user import User
from app.services.draft_service import DraftService
from app.services.errors import PayloadTooLarge
from tests.factories import make_user


class _FakeUserRepo:
    """Pure in-memory double — the service only calls ``update``."""

    async def update(self, user: User) -> User:
        return user


def _service(*, max_bytes: int = 1024) -> DraftService:
    return DraftService(users=_FakeUserRepo(), max_bytes=max_bytes)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_returns_nothing_when_draft_unset() -> None:
    user = make_user()
    payload, updated_at = await _service().get(actor=user)
    assert payload is None
    assert updated_at is None


@pytest.mark.asyncio
async def test_set_persists_payload_and_stamps_time() -> None:
    user = make_user()
    body: dict[str, Any] = {"case_id": "C1", "payload": {"primary_target": {}}}
    saved, updated_at = await _service().set(actor=user, payload=body)
    assert saved == body
    assert user.draft == body
    assert user.draft_updated_at is not None
    assert updated_at == user.draft_updated_at


@pytest.mark.asyncio
async def test_set_rejects_oversized_payload() -> None:
    user = make_user()
    huge = {"blob": "x" * 5000}
    with pytest.raises(PayloadTooLarge):
        await _service(max_bytes=1024).set(actor=user, payload=huge)
    assert user.draft is None
    assert user.draft_updated_at is None


@pytest.mark.asyncio
async def test_clear_wipes_both_columns() -> None:
    user = make_user()
    await _service().set(actor=user, payload={"hello": "world"})
    assert user.draft is not None
    await _service().clear(actor=user)
    assert user.draft is None
    assert user.draft_updated_at is None
