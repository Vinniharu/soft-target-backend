"""Per-user report draft persistence.

A draft is a single free-form JSON blob attached to the user row. It
survives browser refreshes and machine restarts so an investigator can
resume in-progress work after a power outage. There is at most one
draft per user; promoting it to a real report and clearing it are
client-driven (call POST /reports then DELETE /reports/draft).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.errors import PayloadTooLarge

DEFAULT_MAX_BYTES = 256 * 1024


class DraftService:
    def __init__(
        self, *, users: UserRepository, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> None:
        self._users = users
        self._max_bytes = max_bytes

    async def get(
        self, *, actor: User
    ) -> tuple[dict[str, Any] | None, datetime | None]:
        return actor.draft, actor.draft_updated_at

    async def set(
        self, *, actor: User, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], datetime]:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self._max_bytes:
            raise PayloadTooLarge(
                f"draft exceeds {self._max_bytes} bytes (got {len(encoded)})"
            )
        actor.draft = payload
        actor.draft_updated_at = datetime.now(UTC)
        await self._users.update(actor)
        assert actor.draft_updated_at is not None
        return actor.draft, actor.draft_updated_at

    async def clear(self, *, actor: User) -> None:
        actor.draft = None
        actor.draft_updated_at = None
        await self._users.update(actor)
