"""DraftService behaviour (multi-draft).

These exercise the service against an in-memory ``DraftRepository``
double — they verify per-user listing, the 10-cap, the 256 KB cap,
cross-user isolation (404, not 403), and update/delete semantics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.models.draft import Draft
from app.models.user import User
from app.repositories.errors import NotFoundError
from app.schemas.draft import DraftCreate, DraftUpdate
from app.services.draft_service import DraftService
from app.services.errors import Conflict, NotFound, PayloadTooLarge
from tests.factories import make_user


class _FakeDraftRepo:
    """In-memory double — keyed by id, ordered by updated_at desc on list."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, Draft] = {}
        self._seq = 0

    def _next_now(self) -> datetime:
        # Windows clock resolution can stamp two adjacent calls with
        # identical timestamps; offset by a monotonic microsecond
        # counter so list ordering tests stay deterministic.
        self._seq += 1
        return datetime.now(UTC) + timedelta(microseconds=self._seq)

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        title: str | None,
        payload: dict[str, Any],
    ) -> Draft:
        now = self._next_now()
        draft = Draft(user_id=user_id, title=title, payload=payload)
        draft.id = uuid.uuid4()
        draft.created_at = now
        draft.updated_at = now
        self._rows[draft.id] = draft
        return draft

    async def get(self, draft_id: uuid.UUID) -> Draft:
        try:
            return self._rows[draft_id]
        except KeyError as exc:
            raise NotFoundError(f"draft {draft_id} not found") from exc

    async def update(self, draft: Draft) -> Draft:
        draft.updated_at = self._next_now()
        self._rows[draft.id] = draft
        return draft

    async def delete(self, draft: Draft) -> None:
        self._rows.pop(draft.id, None)

    async def list_for_user(
        self, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[Draft], int]:
        rows = [d for d in self._rows.values() if d.user_id == user_id]
        rows.sort(key=lambda d: d.updated_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    async def count_for_user(self, *, user_id: uuid.UUID) -> int:
        return sum(1 for d in self._rows.values() if d.user_id == user_id)


def _service(*, max_bytes: int = 1024, max_per_user: int = 3) -> DraftService:
    return DraftService(
        drafts=_FakeDraftRepo(),  # type: ignore[arg-type]
        max_bytes=max_bytes,
        max_per_user=max_per_user,
    )


async def _seed(svc: DraftService, user: User, n: int) -> list[Draft]:
    """Helper — bypass the cap by reaching into the repo directly."""

    repo = svc._drafts  # noqa: SLF001
    rows: list[Draft] = []
    for i in range(n):
        d = await repo.create(  # type: ignore[attr-defined]
            user_id=user.id, title=f"draft {i}", payload={"i": i}
        )
        rows.append(d)
    return rows


@pytest.mark.asyncio
async def test_list_returns_only_callers_drafts() -> None:
    alice = make_user()
    bob = make_user()
    svc = _service()
    await _seed(svc, alice, 2)
    await _seed(svc, bob, 1)

    drafts, total = await svc.list(actor=alice)
    assert total == 2
    assert all(d.user_id == alice.id for d in drafts)


@pytest.mark.asyncio
async def test_create_persists_payload_and_title() -> None:
    alice = make_user()
    svc = _service()
    payload = DraftCreate(title="My Draft", payload={"a": 1})
    draft = await svc.create(actor=alice, payload=payload)
    assert draft.user_id == alice.id
    assert draft.title == "My Draft"
    assert draft.payload == {"a": 1}
    assert draft.created_at is not None
    assert draft.updated_at is not None


@pytest.mark.asyncio
async def test_create_enforces_per_user_cap() -> None:
    alice = make_user()
    svc = _service(max_per_user=3)
    for _ in range(3):
        await svc.create(actor=alice, payload=DraftCreate(payload={}))
    with pytest.raises(Conflict):
        await svc.create(actor=alice, payload=DraftCreate(payload={}))


@pytest.mark.asyncio
async def test_create_rejects_oversized_payload() -> None:
    alice = make_user()
    svc = _service(max_bytes=512)
    huge = {"blob": "x" * 5000}
    with pytest.raises(PayloadTooLarge):
        await svc.create(actor=alice, payload=DraftCreate(payload=huge))


@pytest.mark.asyncio
async def test_get_returns_404_for_other_users_draft() -> None:
    alice = make_user()
    bob = make_user()
    svc = _service()
    bob_drafts = await _seed(svc, bob, 1)

    with pytest.raises(NotFound):
        await svc.get(draft_id=bob_drafts[0].id, actor=alice)


@pytest.mark.asyncio
async def test_update_replaces_payload_and_keeps_title_when_omitted() -> None:
    alice = make_user()
    svc = _service()
    draft = await svc.create(
        actor=alice, payload=DraftCreate(title="Keep me", payload={"a": 1})
    )

    updated = await svc.update(
        draft_id=draft.id,
        actor=alice,
        payload=DraftUpdate(payload={"b": 2}),
    )
    assert updated.payload == {"b": 2}
    assert updated.title == "Keep me"


@pytest.mark.asyncio
async def test_update_rejects_oversized_payload() -> None:
    alice = make_user()
    svc = _service(max_bytes=512)
    draft = await svc.create(
        actor=alice, payload=DraftCreate(payload={})
    )
    huge = {"blob": "x" * 5000}
    with pytest.raises(PayloadTooLarge):
        await svc.update(
            draft_id=draft.id,
            actor=alice,
            payload=DraftUpdate(payload=huge),
        )


@pytest.mark.asyncio
async def test_upsert_active_creates_when_user_has_no_drafts() -> None:
    alice = make_user()
    svc = _service()
    draft = await svc.upsert_active(
        actor=alice, payload=DraftUpdate(payload={"a": 1})
    )
    assert draft.user_id == alice.id
    assert draft.payload == {"a": 1}
    drafts, total = await svc.list(actor=alice)
    assert total == 1
    assert drafts[0].id == draft.id


@pytest.mark.asyncio
async def test_upsert_active_replaces_most_recent_when_one_exists() -> None:
    alice = make_user()
    svc = _service(max_per_user=5)
    older = await svc.create(
        actor=alice, payload=DraftCreate(payload={"first": True})
    )
    newer = await svc.create(
        actor=alice, payload=DraftCreate(payload={"second": True})
    )
    updated = await svc.upsert_active(
        actor=alice, payload=DraftUpdate(payload={"third": True})
    )
    # The most-recently-updated draft is the second one.
    assert updated.id == newer.id
    assert updated.payload == {"third": True}
    # The older draft remains untouched.
    untouched = await svc.get(draft_id=older.id, actor=alice)
    assert untouched.payload == {"first": True}


@pytest.mark.asyncio
async def test_delete_removes_only_own_draft() -> None:
    alice = make_user()
    bob = make_user()
    svc = _service()
    bob_drafts = await _seed(svc, bob, 1)
    alice_draft = await svc.create(
        actor=alice, payload=DraftCreate(payload={})
    )

    # Bob's draft id is not deletable from Alice's session.
    with pytest.raises(NotFound):
        await svc.delete(draft_id=bob_drafts[0].id, actor=alice)

    await svc.delete(draft_id=alice_draft.id, actor=alice)
    drafts, total = await svc.list(actor=alice)
    assert total == 0
    assert drafts == []
