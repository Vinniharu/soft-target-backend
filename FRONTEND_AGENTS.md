# Frontend Integration Notes — Soft Target Backend

**Audience:** the frontend team / coding agent. **Source of truth for the API contract:** `API.md` in this repo. This file summarizes only what changed in the most recent backend update so the frontend can be updated to match.

If you are an AI assistant reading this: treat every section below as a checklist item that must be reflected in the frontend code before the next release.

---

## Base URL & deployment

| Environment | URL |
|-------------|-----|
| Local dev   | `http://localhost:8000` |
| VPS         | `http://41.242.54.70:4382` *(HTTP only — TLS pending)* |

> **Heads-up for security:** the VPS is currently HTTP-only. Treat any session token returned from this URL as exposable on the wire. Once HTTPS is provisioned the URL/scheme will change — read it from an env var, don't hardcode it.

CORS allowed origins are configured server-side. If you stand up a new frontend host, ask the backend to add it to `CORS_ALLOWED_ORIGINS` and restart the service.

---

## Change 1 — Login response now includes `role`

**Endpoint:** `POST /api/v1/auth/login`

**Old response shape:**
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**New response shape:**
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900,
  "role": "user"
}
```

`role` is `"user"` or `"admin"`.

### What the frontend must do

- **Read `role` from the login response** and use it to decide the post-login landing page. Do **not** redirect to `/app/dashboard` (that route doesn't exist in the frontend tree — you saw a 404 when testing this).
- Suggested routing:
  - `role === "admin"` → admin dashboard route (e.g. `/admin`)
  - `role === "user"` → investigator dashboard route (e.g. `/reports`)
- Cache the role in your auth store alongside the tokens. Re-fetch via `/auth/me` after a refresh, since the role can change if an admin updates the account.

---

## Change 2 — New endpoint `GET /api/v1/auth/me`

Returns the currently-authenticated user. Requires `Authorization: Bearer <access_token>`.

**Response 200:**
```json
{
  "id": "uuid",
  "email": "investigator@example.com",
  "name": "Alice Investigator",
  "role": "user",
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "deleted_at": null
}
```

**Errors:** `401` if the token is missing, invalid, or expired (use the existing refresh-then-retry path).

### What the frontend must do

- Call `/auth/me` on app boot (after restoring tokens from storage) to verify the session is still valid and to populate the user profile (name, role, email) before rendering anything role-gated.
- Use the response — not the JWT payload — as the source of truth for the displayed name and role. Don't decode the JWT client-side.

---

## Change 3 — Admin-only report write endpoints moved

The endpoints for editing and deleting reports have moved from the user-facing `/reports` namespace to the admin namespace. Non-admins can no longer reach them at all (the user-facing routes were removed, not just guarded).

| Old (gone) | New |
|------------|-----|
| `PATCH /api/v1/reports/{report_id}` | `PATCH /api/v1/admin/reports/{report_id}` |
| `DELETE /api/v1/reports/{report_id}` | `DELETE /api/v1/admin/reports/{report_id}` |

Request and response bodies are unchanged — only the URL changed.

### What the frontend must do

- Update any "edit report" or "delete report" call site that hits the old URL. The old paths return `404` now.
- Hide the edit/delete buttons in the UI when `role !== "admin"`. The backend will refuse with `403`, but the buttons should never appear for regular investigators in the first place.
- The endpoints that **stayed** under `/reports` (still callable by any authenticated user):
  - `POST /api/v1/reports` — create
  - `GET /api/v1/reports` — list (users see only their own; admins see all)
  - `GET /api/v1/reports/{report_id}` — fetch one
  - `GET /api/v1/reports/{report_id}/pdf` — download PDF

---

## Change 4 — `name` field on users (required)

The `users` table has a new `name` column. All user payloads now include it.

**`POST /api/v1/admin/users` request — `name` is now required:**
```json
{
  "email": "newagent@example.com",
  "password": "at-least-twelve-chars",
  "name": "Alice Investigator",
  "role": "user"
}
```

- `name`: 1–100 characters. Required on create, optional on update.
- Sending the old payload (no `name`) will return `422 Unprocessable Entity`.

**`PATCH /api/v1/admin/users/{user_id}` — `name` is optional:**
```json
{ "name": "Alice's New Display Name" }
```

**`UserRead` (returned by `GET /admin/users`, `GET /auth/me`, etc.) now always includes `name`:**
```json
{
  "id": "uuid",
  "email": "...",
  "name": "Alice Investigator",
  "role": "user",
  "created_at": "...",
  "updated_at": "...",
  "deleted_at": null
}
```

### What the frontend must do

- **Add a `name` field to the "create user" form** in the admin user-management UI. Validate 1–100 chars client-side; the backend will reject empty or over-length values with `422`.
- **Add `name` to the "edit user" form**, optional.
- **Render `name` in the user list, profile chip, and any "created by" or "edited by" labels.** Pre-existing accounts will show `""` (empty string) until edited — display them as something like *"(no name set)"* so they're visually distinct.
- The login flow does not return `name` in the token response — fetch it via `/auth/me` after login if you need to display it on the dashboard.

---

## Change 5 — Login is rate-limited again

`POST /api/v1/auth/login` is rate-limited to **5 attempts per 15 minutes per IP** (configurable server-side).

A 6th attempt within the window returns:
```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{ "detail": "too many requests" }
```

### What the frontend must do

- Handle `429` on the login form with a user-facing message like *"Too many login attempts. Please wait a few minutes and try again."* — do not silently retry, and do not show the same generic *"invalid email or password"* error.
- The window resets on a sliding basis, not all at once at the 15-minute mark. Don't surface a precise countdown — the API doesn't return one.
- Successful logins do **not** clear the bucket, so a user fat-fingering their password 5 times in a row will be locked out from that IP for the window even after eventually getting the password right. This is intentional.

---

## Change 6 — Per-user report drafts (server-backed autosave)

There is now one server-side draft slot per user, intended for power-outage and browser-crash recovery on the report-creation form. Three endpoints:

| Method | URL | Purpose |
|--------|-----|---------|
| `GET`    | `/api/v1/reports/draft` | Load the current user's draft on app boot |
| `PUT`    | `/api/v1/reports/draft` | Save (autosave) — replaces the existing draft |
| `DELETE` | `/api/v1/reports/draft` | Clear the draft after promoting it to a real report |

All three require a normal `Authorization: Bearer <access_token>` header. Each user has at most one draft. Drafts are user-private — admins do not see other users' drafts.

**Request body for PUT:**
```json
{
  "payload": { /* anything — frontend decides shape */ }
}
```

The recommended convention is to mirror the `POST /reports` body so promoting is straightforward:
```json
{
  "payload": {
    "case_id": "CASE-2026-0001",
    "payload": {
      "primary_target": { "name": "Subject A", "imei_numbers": ["..."] },
      "soft_targets": [],
      "summary": null
    }
  }
}
```

**Response (GET and PUT):**
```json
{
  "payload": { /* the JSON you saved */ },
  "updated_at": "2026-04-17T10:15:32.481Z"
}
```
GET returns `{ "payload": null, "updated_at": null }` when no draft exists.

### What the frontend must do

- **On the report-creation page mount:** call `GET /reports/draft`. If `payload` is non-null, hydrate the form from it and show a banner like *"Restored draft from {updated_at}."*
- **While the user types:** debounce-save to `PUT /reports/draft` (recommended cadence: 1.5–3 seconds after the last keystroke, plus a save on blur). The debounce is mandatory — saving on every keystroke wastes server cycles and is unnecessary for power-outage recovery.
- **When the user clicks Submit and `POST /reports` succeeds:** call `DELETE /reports/draft` to clear the slot. If the DELETE fails, ignore it — the next successful `PUT` will overwrite the stale draft anyway.
- **When the user explicitly clicks "Discard draft":** call `DELETE /reports/draft` and reset the form.

### Constraints and edge cases

- **Size cap: 256 KB** of serialized JSON per draft. The server returns `413 Payload Too Large` if you exceed it. In practice this is well above a maxed-out report (≈150 KB), but if you ever start embedding base64 images or similar, watch for it.
- **No schema validation on the draft contents.** The server stores whatever JSON object you `PUT` under `payload`. This is intentional — drafts are partial by definition. Validation only happens when you submit the real `POST /reports`.
- **One draft per user, server-side.** If the user has two browser tabs open on the report form, the last `PUT` wins. There is no merge logic. If you want per-tab isolation, layer that in client-side (e.g. each tab gets its own local cache and PUTs only when the tab is active).
- **No conflict detection.** If the user has the form open on two devices, last write wins silently. Surfacing this in the UI requires a frontend convention (e.g. compare the `updated_at` you last saw against the one the GET returns on focus).
- **Drafts persist across logins** — they live on the user row, not the session. Logging out doesn't clear them.
- **Drafts are not auto-cleared when a report is created** — your frontend has to call `DELETE /reports/draft` explicitly after a successful submit.
- **No audit logging on draft writes.** They'd flood the audit log under autosave.
- **The draft does not show up in `/auth/me`.** If you need to know whether a draft exists without loading it, just call `GET /reports/draft` — it's a single row lookup and returns nulls cheaply.

### Updated migration checklist (additions)

- [ ] Wire `GET /reports/draft` into the report-creation page mount.
- [ ] Add debounced `PUT /reports/draft` to the form's onChange handler.
- [ ] Add `DELETE /reports/draft` to the post-submit success path.
- [ ] Show a "draft restored" banner with the `updated_at` timestamp.
- [ ] Add a manual "Discard draft" button that calls `DELETE`.
- [ ] Handle `413` from PUT with a "draft too large to save" message (rare, but worth a one-line catch).

---

## Change 7 — `/auth/me` and the `name` field together close the "who created this report" gap

Reports already carry the creator's `user_id`. To show *"Created by Alice"* in the UI:

1. Fetch the report (`GET /reports/{id}`) — gives you `user_id`.
2. The admin-only `GET /admin/users` returns the user list with names. For non-admins viewing their own reports, the name is the *current* user's name from `/auth/me`.

There's no public `GET /users/{id}` endpoint — only admins can list users. For non-admin views of their own reports, just show the current user's name (since they are the creator).

---

## Things that did **not** change

- **Auth flow** — JWT bearer + refresh token rotation works exactly as before. The `/auth/refresh` endpoint, single-use refresh tokens, and the auto-refresh-on-401 pattern are unchanged.
- **Report payload schema** — `ReportCreate`, `ReportPayload`, `PrimaryTarget`, `SoftTarget`, `Coordinates`, `summary` shapes are all the same.
- **PDF download** — `GET /reports/{id}/pdf` is unchanged.
- **Audit log endpoint** — `GET /admin/audit` shape is unchanged.
- **Error envelope** — still `{ "detail": "..." }` on every error.

---

## Migration checklist for the frontend repo

In rough priority order:

- [ ] **Fix the post-login redirect** — read `role` from the login response and route accordingly. This is what was breaking when you saw `/app/dashboard` 404s.
- [ ] Add `/auth/me` call to app boot, store `{ id, email, name, role }` in your auth store.
- [ ] Update report-edit and report-delete call sites to the new `/admin/reports/{id}` URLs.
- [ ] Add `name` to admin user-create form (required, 1–100 chars).
- [ ] Add `name` to admin user-edit form (optional).
- [ ] Render `name` in the admin user list (handle empty-string for legacy accounts).
- [ ] Render `name` in the current-user profile UI (pulled from `/auth/me`).
- [ ] Handle `429` on the login form with a "wait and retry" message.
- [ ] Hide admin-only buttons (edit/delete report, user management nav) when `role !== "admin"`.

---

## Quick reference — endpoint matrix after this update

### Public (no auth)
- `POST /api/v1/auth/login` — rate-limited
- `POST /api/v1/auth/refresh`

### Authenticated (any role)
- `GET /api/v1/auth/me`
- `POST /api/v1/reports`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{id}`
- `GET /api/v1/reports/{id}/pdf`
- `GET /api/v1/reports/draft`
- `PUT /api/v1/reports/draft`
- `DELETE /api/v1/reports/draft`

### Admin only (`role === "admin"`)
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{id}`
- `DELETE /api/v1/admin/users/{id}`
- `PATCH /api/v1/admin/reports/{id}` *(moved here from `/reports`)*
- `DELETE /api/v1/admin/reports/{id}` *(moved here from `/reports`)*
- `GET /api/v1/admin/audit`

For the full request/response shapes of any endpoint above, see `API.md` in this repo.
