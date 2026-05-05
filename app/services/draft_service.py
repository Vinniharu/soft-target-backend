"""Per-user draft persistence (multi-draft).

Each draft is its own row owned by a single user. The frontend can keep
several drafts in flight at once and switch between them. Promotion to
a real report stays client-driven: read draft → ``POST /reports`` →
``DELETE /reports/drafts/{id}``.

Caps:
- 10 drafts per user (creating an 11th raises ``Conflict``).
- 256 KB serialized JSON per draft (raises ``PayloadTooLarge``).

Cross-user isolation: every read/write is scoped to ``actor.id``. A
caller asking for someone else's draft id gets ``NotFound`` (we use
``404`` rather than ``403`` so we don't confirm a draft id exists).
"""

from __future__ import annotations

import json
import uuid

from app.models.draft import Draft
from app.models.user import User
from app.repositories.draft_repo import DraftRepository
from app.repositories.errors import NotFoundError
from app.schemas.draft import DraftCreate, DraftUpdate
from app.services.errors import Conflict, NotFound, PayloadTooLarge

DEFAULT_MAX_BYTES = 256 * 1024
DEFAULT_MAX_PER_USER = 10


class DraftService:
    def __init__(
        self,
        *,
        drafts: DraftRepository,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_per_user: int = DEFAULT_MAX_PER_USER,
    ) -> None:
        self._drafts = drafts
        self._max_bytes = max_bytes
        self._max_per_user = max_per_user

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list(
        self, *, actor: User, limit: int = 50, offset: int = 0
    ) -> tuple[list[Draft], int]:
        return await self._drafts.list_for_user(
            user_id=actor.id, limit=limit, offset=offset
        )

    async def get(self, *, draft_id: uuid.UUID, actor: User) -> Draft:
        try:
            draft = await self._drafts.get(draft_id)
        except NotFoundError as exc:
            raise NotFound("draft not found") from exc
        if draft.user_id != actor.id:
            # Treat cross-user access exactly like missing — do not leak
            # the existence of another user's draft id.
            raise NotFound("draft not found")
        return draft

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self, *, actor: User, payload: DraftCreate
    ) -> Draft:
        self._enforce_payload_size(payload.payload)
        existing = await self._drafts.count_for_user(user_id=actor.id)
        if existing >= self._max_per_user:
            raise Conflict(
                f"draft limit reached "
                f"(have {existing} of {self._max_per_user}); "
                "delete an existing draft before creating a new one"
            )
        return await self._drafts.create(
            user_id=actor.id,
            title=payload.title,
            payload=payload.payload,
        )

    async def update(
        self,
        *,
        draft_id: uuid.UUID,
        actor: User,
        payload: DraftUpdate,
    ) -> Draft:
        draft = await self.get(draft_id=draft_id, actor=actor)
        if payload.payload is not None:
            self._enforce_payload_size(payload.payload)
            draft.payload = payload.payload
        if payload.title is not None:
            draft.title = payload.title
        return await self._drafts.update(draft)

    async def delete(self, *, draft_id: uuid.UUID, actor: User) -> None:
        draft = await self.get(draft_id=draft_id, actor=actor)
        await self._drafts.delete(draft)

    async def upsert_active(
        self, *, actor: User, payload: DraftUpdate
    ) -> Draft:
        """Convenience for the simple-autosave UX: replace the caller's
        most-recently-updated draft, or create a new one if they have
        none.

        Use this when the frontend doesn't want to track ids. Multi-draft
        callers should use :meth:`create` and :meth:`update` directly so
        they always know which draft is being written.

        Behaviour:
        - 0 drafts: create one with the given title (or null) and payload
          (or empty dict). Subject to the 10-per-user cap.
        - 1+ drafts: update the most-recent (by ``updated_at``); same
          partial-update semantics as :meth:`update` (omit a field to
          leave it alone).
        """

        rows, _ = await self._drafts.list_for_user(
            user_id=actor.id, limit=1, offset=0
        )
        if not rows:
            create_payload = DraftCreate(
                title=payload.title,
                payload=payload.payload or {},
            )
            return await self.create(actor=actor, payload=create_payload)

        draft = rows[0]
        if payload.payload is not None:
            self._enforce_payload_size(payload.payload)
            draft.payload = payload.payload
        if payload.title is not None:
            draft.title = payload.title
        return await self._drafts.update(draft)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _enforce_payload_size(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self._max_bytes:
            raise PayloadTooLarge(
                f"draft exceeds {self._max_bytes} bytes (got {len(encoded)})"
            )
