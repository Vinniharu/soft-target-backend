# Soft Target — Multi-Draft Reports

This document is the frontend handoff for the move from a single-draft-per-user model to multiple drafts per user. Every backend change is in `main` and the alembic migration carries existing single drafts forward, so users won't lose any in-progress work.

For the canonical request/response shape of every other endpoint, see **API.md**. This file covers only the draft changes.

---

## 1. Overview

Today (pre-release): each user has exactly **one** draft, stored in a JSONB column on their user row. The frontend autosaves to `PUT /api/v1/reports/draft` and reloads on app boot. Starting a new report overwrites the existing one — there's no way to keep two reports half-finished at once.

After this release: drafts are first-class records. Each user can have up to **10 drafts** in flight, each with its own UUID, optional title, and JSON payload. Switching between drafts is just a `GET /api/v1/reports/drafts/{id}` call; creating a new one doesn't touch existing drafts.

What hasn't changed:
- The payload is still free-form JSON. The server doesn't validate its shape — that's still a frontend convention.
- Promotion to a real report is still client-driven: read draft → `POST /api/v1/reports` → `DELETE /api/v1/reports/drafts/{id}`. There is no server-side `/promote` endpoint.
- Drafts are strictly per-user. Org owners and admins **do not** see other users' drafts.

---

## 2. Migration & deployment

### Database

`alembic upgrade head` applies migration `0005_drafts_table` in one transaction:

1. Creates table `drafts(id, user_id, title, payload, created_at, updated_at)` with FK to `users(id)` (`ON DELETE CASCADE`) and an index on `(user_id, updated_at DESC)`.
2. **Backfill**: every non-null `users.draft` becomes one row in `drafts` with `title=NULL` and `created_at = updated_at = users.draft_updated_at`.
3. Drops `users.draft` and `users.draft_updated_at`.

The migration is idempotent at the data level — existing single drafts come across as one entry per user, no work lost.

### Deploy

```bash
softtarget-deploy   # pulls, alembic upgrade, restart
```

After deploy, every user that had a draft will see exactly one entry in `GET /api/v1/reports/drafts` containing the same payload they had before. They can keep editing it, or create up to nine more.

### Rollback

`alembic downgrade -1` re-adds the legacy columns and copies back the **most-recently-updated** draft per user. Anything beyond the first draft per user is dropped — a single-draft model can't fit more than one. Don't roll back unless you have to.

---

## 3. Endpoint reference

All five routes require `Authorization: Bearer <access_token>`. Authorization is implicit: every read and write is scoped server-side to the caller's `user_id`. There is no path-level authorization — any authenticated caller may call any of these — but they only ever see/touch their own drafts.

### `GET /api/v1/reports/drafts`

List the caller's drafts. Returns summaries only (no `payload` field) so the list view stays cheap.

**Query params**
- `limit` (1–200, default 50)
- `offset` (≥ 0, default 0)

**Response 200**
```json
{
  "items": [
    {
      "id": "0d0f7c8a-1234-5678-90ab-cdef01234567",
      "title": "Investigation A — first pass",
      "created_at": "2026-06-01T09:15:00Z",
      "updated_at": "2026-06-02T14:30:00Z"
    },
    {
      "id": "1e1f8d9b-...",
      "title": null,
      "created_at": "2026-05-30T18:00:00Z",
      "updated_at": "2026-05-30T18:00:00Z"
    }
  ],
  "total": 2
}
```

Order is **most-recently-updated first**.

`title` is optional; expect `null` for drafts the user never named (and for everything carried over from the legacy single-draft column).

---

### `POST /api/v1/reports/drafts`

Create a new draft.

**Request**
```json
{
  "title": "Investigation B — initial intake",
  "payload": {
    "case_id": "CASE-2026-0042",
    "payload": {
      "primary_target": { "name": "Subject B" }
    }
  }
}
```

Both fields are optional:
- `title`: 1–200 chars, or omit. Use it for the list view; it doesn't affect anything else.
- `payload`: any JSON object including `{}`.

**Response 201** — full `DraftRead` (same as `GET /api/v1/reports/drafts/{id}` below).

**Errors**
- `409` — caller already has 10 drafts. Delete one before creating another.
- `413` — payload exceeds the 256 KB serialized cap.
- `422` — title too long, or extra/unknown fields in the body (`extra="forbid"`).

---

### `PUT /api/v1/reports/drafts` (no id) — singleton autosave shortcut

Convenience endpoint for the simple autosave UX where the frontend doesn't want to track draft ids. Replaces the caller's most-recently-updated draft, or creates a new one if they have none.

**Request** (same shape as `PUT /api/v1/reports/drafts/{id}`)
```json
{
  "title": "optional title",
  "payload": { /* whatever form state */ }
}
```

Both fields are optional (`title` defaults to `null`, `payload` defaults to `{}` on first create). On the update path, omitted fields leave the existing value alone — same partial-update semantics as the by-id PUT.

**Response 200** — full `DraftRead` of the row that was created or updated.

**Errors**
- `409` — happens only on the create path: the caller has 0 drafts technically wouldn't trigger this, but if a race causes the count check to see 10 drafts before the singleton update path is hit, you'll see this. In practice, `200` is the only realistic response once a draft exists.
- `413` — payload exceeds 256 KB.
- `422` — title too long or extra fields.

**When to use this vs `PUT /{id}`:**
- Use this if your frontend treats drafting as a singleton (one open draft at a time) and you don't want to track ids in local state.
- Use `PUT /{id}` if your UI actually exposes multiple drafts, lets the user switch between them, or has a dedicated drafts page. The id-based form is the only correct way to write to a *specific* draft.

---

### `GET /api/v1/reports/drafts/{draft_id}`

Fetch one of the caller's drafts including the full payload.

**Response 200**
```json
{
  "id": "0d0f7c8a-1234-5678-90ab-cdef01234567",
  "title": "Investigation A — first pass",
  "payload": {
    "case_id": "CASE-2026-0001",
    "payload": {
      "primary_target": { "name": "Subject A", "imei_numbers": [] },
      "soft_targets": [],
      "summary": null
    }
  },
  "created_at": "2026-06-01T09:15:00Z",
  "updated_at": "2026-06-02T14:30:00Z"
}
```

**Errors**
- `404` — no draft with this id, or this id belongs to another user. We **deliberately use 404 rather than 403** for cross-user access so callers can't enumerate other users' draft ids.

---

### `PUT /api/v1/reports/drafts/{draft_id}`

Replace one of the caller's drafts. Idempotent — call as often as you like (debounced autosave is fine).

**Request** (both optional, at least one expected)
```json
{
  "title": "Investigation A — revised after intel",
  "payload": {
    "case_id": "CASE-2026-0001",
    "payload": { "primary_target": { "name": "Subject A" } }
  }
}
```

Semantics:
- `title`: send a string to set/replace it. Omit (or send `null`) to leave the existing title alone. There is no "clear title" — to wipe the title you'd need to recreate the draft (rare).
- `payload`: send an object to replace the stored payload. Omit (or send `null`) to leave the existing payload alone — useful when the user only renames the draft.

`updated_at` is bumped on every successful PUT regardless of which fields changed.

**Response 200** — full `DraftRead` with the new state.

**Errors**
- `404` — draft id doesn't exist or belongs to another user.
- `413` — new payload exceeds 256 KB.
- `422` — invalid body (e.g. title too long, extra fields).

---

### `DELETE /api/v1/reports/drafts/{draft_id}`

Hard-delete one of the caller's drafts. There is no soft-delete; the row is gone.

**Response** — `204 No Content`. Idempotent in spirit, but a second call on the same id will return `404` because the row is genuinely gone.

**Errors**
- `404` — draft id doesn't exist or belongs to another user.

---

## 4. Caps & error matrix at a glance

| Trigger | Status | Body |
|---|---|---|
| 11th draft created | `409` | `{"detail":"draft limit reached (have 10 of 10); delete an existing draft before creating a new one"}` |
| Payload >256 KB on create or PUT | `413` | `{"detail":"draft exceeds 262144 bytes (got NNN)"}` |
| Title >200 chars | `422` | Pydantic validation error |
| Extra fields in body (`extra="forbid"`) | `422` | Pydantic validation error |
| Reading / writing another user's draft id | `404` | `{"detail":"draft not found"}` |
| Missing or expired token | `401` | `{"detail":"not authenticated"}` |
| Caller's organisation soft-deleted | `401` | `{"detail":"organisation deactivated"}` |

---

## 5. Frontend wiring

### Replacing the singleton calls

Wherever the old code did this:

```js
// OLD — single-draft
const { payload, updated_at } = await api.get("/reports/draft");
await api.put("/reports/draft", { payload: form });
await api.delete("/reports/draft");
```

…replace with one of two patterns depending on the UX:

**Pattern A — "session" (drop-in for the old behaviour):**
The frontend keeps a `currentDraftId` in local state, and:
- On boot, list drafts. If there's exactly one, open it. If there are several, show a picker. If there are none, create a fresh one.
- Autosave PUTs `/reports/drafts/{currentDraftId}` with the form state.
- "New report" clears the in-memory form and creates a new draft via `POST /reports/drafts` (don't reuse the existing `currentDraftId`).

**Pattern B — "drafts list" (full multi-draft UX):**
A dedicated drafts page lists every draft (`GET /reports/drafts`), each row showing `title`, `updated_at`, and "Open" / "Delete" buttons. The editor opens via `GET /reports/drafts/{id}`, autosaves via `PUT /reports/drafts/{id}`, and "Discard" calls `DELETE`. "New report" creates a fresh draft and navigates to it.

Pattern B is the one this release was built for; Pattern A is a stop-gap if the UI work is rolled out incrementally.

### Autosave conventions

- Debounce PUTs to 1–2 seconds of idle keystrokes — same as the old singleton autosave.
- Always send the full state in `payload` (PUT replaces; we don't merge).
- After a successful `POST /reports`, follow up with `DELETE /reports/drafts/{id}` for the draft you just promoted. The server doesn't auto-delete.

### List-view UI suggestions

- Show `title || "Untitled draft"` as the row label.
- Sort by `updated_at` desc (the server already does that, but the frontend can re-sort if it has fresher local edits).
- A "10/10" indicator near the "New report" button when the user is at the cap helps explain why the next create might 409.

### Error handling

- `409` on create — surface "You're at the 10-draft limit. Delete an existing draft to start a new one." with a button that opens the drafts list.
- `413` — surface "Your draft is too large to save (over 256 KB). Trim notes or remove unused soft targets." This is rare in practice.
- `404` on get/put/delete — the draft was deleted or never existed. Pop the user back to the drafts list and refresh it.

---

## 6. What didn't change

- `POST /api/v1/reports`, `GET /api/v1/reports`, `GET /api/v1/reports/{id}`, `PATCH /api/v1/reports/{id}`, `DELETE /api/v1/reports/{id}`, `GET /api/v1/reports/{id}/pdf` — same shape, same semantics.
- `/auth/login`, `/auth/refresh`, `/auth/me` — same.
- The 256 KB JSON cap on draft payloads — same number, different scope (per draft instead of per user).
- The 1–200 chars rule on titles is **new** — there was no title field before.

---

## 7. Verification checklist

After deploying to the VPS:

1. `softtarget-deploy` — alembic should print `Running upgrade 0004_organisations -> 0005_drafts_table`.
2. Pre-existing single draft holders (if any) call `GET /api/v1/reports/drafts` and see one row with their old payload and a `null` title.
3. As any user:
   - `POST /api/v1/reports/drafts` 10 times → 10 × `201`. The 11th → `409`.
   - `GET /api/v1/reports/drafts` → 10 summaries, ordered by `updated_at` desc.
   - `PUT /api/v1/reports/drafts/{id}` with a new payload → `200`, `updated_at` advances.
   - `GET /api/v1/reports/drafts/{id}` → full draft with the new payload.
   - `DELETE /api/v1/reports/drafts/{id}` → `204`. Subsequent `GET` of that id → `404`.
4. As another user (cross-user isolation):
   - `GET /api/v1/reports/drafts/{otherUsersId}` → `404`.
   - `PUT /api/v1/reports/drafts/{otherUsersId}` → `404`.
5. `POST /api/v1/reports/drafts` with a payload over 256 KB → `413`.

If any of those return something other than the listed status, capture the failing response.
