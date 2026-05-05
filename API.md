# Soft Target Backend — API Reference

Reference for the Next.js frontend (or any client) that talks to this API.

## Base URL

| Environment | URL |
|-------------|-----|
| Local dev   | `http://localhost:8000` |
| VPS (current) | `http://41.242.54.70:4382` |

All endpoints live under `/api/v1`. Example: `http://41.242.54.70:4382/api/v1/auth/login`.

---

## Authentication

JWT bearer tokens. No public signup — all accounts are created by an admin.

### Flow

1. `POST /api/v1/auth/login` with email + password → receive `access_token` + `refresh_token`
2. Include the access token on every subsequent request:
   ```
   Authorization: Bearer <access_token>
   ```
3. Access tokens expire after **15 minutes** (configurable)
4. When any call returns `401 Unauthorized`, call `POST /api/v1/auth/refresh` with the current refresh token to get a new pair
5. Refresh tokens are **single-use** and rotate on every refresh — always replace the one in storage with the new one from the response
6. Refresh tokens expire after **30 days** (configurable)

### Roles

| Role | Can do |
|---|---|
| `user` | Create reports; view, edit, and download their own reports. Cannot delete. |
| `org_owner` | Everything a `user` can do, plus: see, edit, and delete every report in their organisation; create / edit / soft-delete members of their own organisation. |
| `admin` | Everything an `org_owner` can do, plus: create / edit / soft-delete organisations; create / edit / delete users in any organisation; edit / delete any report; view audit logs. |

Tenant model: every non-admin user belongs to exactly one organisation. Each organisation has exactly one `org_owner`. Reports are stamped with the creator's organisation at write time and stay attributed to that organisation for life. See **UPDATE.md** for the full migration explanation and the visibility matrix.

---

## Error format

All errors return JSON with a `detail` field:

```json
{ "detail": "error message" }
```

Validation errors (422) include field-level details:

```json
{
  "detail": "invalid request",
  "errors": [
    { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error" }
  ]
}
```

### Status codes you'll see

| Code | Meaning |
|------|---------|
| 200  | OK |
| 201  | Created |
| 204  | No Content (delete success) |
| 401  | Missing or invalid token → refresh or re-login |
| 403  | Authenticated but not permitted (e.g. user trying to edit a report) |
| 404  | Resource doesn't exist or has been soft-deleted |
| 409  | Conflict (e.g. email already registered) |
| 413  | Payload too large (e.g. draft body over the per-user cap) |
| 422  | Pydantic validation failed |
| 429  | Too many requests (login rate limit) |
| 500  | Internal error — check server logs |

The backend never returns stack traces or database internals to the client.

---

## Endpoints

### Health

#### `GET /healthz`

Public. No auth required.

**Response 200**
```json
{ "status": "ok" }
```

---

### Authentication

#### `POST /api/v1/auth/login`

Public. Rate-limited to **5 attempts per 15 minutes per IP** (configurable).

**Request**
```json
{
  "email": "investigator@example.com",
  "password": "the-password"
}
```

**Response 200**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "pXzA1BcD2EfG3HiJ4KlMnO5PqRsT6UvW7XyZ",
  "token_type": "bearer",
  "expires_in": 900,
  "role": "user"
}
```

`expires_in` is seconds until the access token expires (900 = 15 min). `role` is `"user"`, `"org_owner"`, or `"admin"` and lets the frontend pick the right post-login landing page without a follow-up call. To learn the caller's tenant (organisation), call `GET /api/v1/auth/me` once after login.

**Errors**
- `401` — invalid email or password (same message either way — doesn't leak account existence)
- `429` — too many login attempts from this IP; wait and retry

---

#### `POST /api/v1/auth/refresh`

Public.

**Request**
```json
{ "refresh_token": "pXzA1BcD2EfG3HiJ4KlMnO5PqRsT6UvW7XyZ" }
```

**Response 200** — same shape as login. The old refresh token is now invalid; save the new one.

**Errors**
- `401` — refresh token invalid, expired, or already used → force re-login

---

#### `GET /api/v1/auth/me`

Returns the currently-authenticated user. Requires `Authorization: Bearer <access_token>`.

**Response 200**
```json
{
  "id": "uuid",
  "email": "investigator@example.com",
  "name": "Alice Investigator",
  "role": "user",
  "organisation": {
    "id": "11111111-2222-3333-4444-555555555555",
    "name": "Acme Investigations Ltd."
  },
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "deleted_at": null
}
```

`organisation` is `null` for admin accounts (admins do not belong to any organisation). For `org_owner` and `user` roles it is always populated.

**Errors**
- `401` — missing, invalid, or expired access token; also `401 organisation deactivated` if the caller's organisation has been soft-deleted

---

### Reports

All endpoints in this section require `Authorization: Bearer <access_token>`.

#### `POST /api/v1/reports`

Create a new report. Any authenticated user. The server generates the PDF and stores it on disk — it's immutable from this point on.

**Request**
```json
{
  "case_id": "CASE-2026-0001",
  "payload": {
    "primary_target": {
      "name": "Subject A",
      "imei_numbers": ["490154203237518", "356938035643809"],
      "phone_numbers": ["+15551234567"],
      "location": "42 Example Street, London",
      "coordinates": { "latitude": 51.5074, "longitude": -0.1278 },
      "notes": "Initial observation from field team"
    },
    "soft_targets": [
      {
        "phone": "+15550009999",
        "location": "Known associate — café on Main Street",
        "coordinates": { "latitude": 51.5100, "longitude": -0.1200 },
        "notes": null
      }
    ],
    "summary": "Preliminary surveillance summary. Subject observed meeting with known associates at 14:30."
  }
}
```

**Validation rules**
- `case_id`: 1–64 chars, required
- `primary_target`: required; all its fields are optional
- `primary_target.imei_numbers`: list, max 16 entries
- `primary_target.phone_numbers`: list, max 16 entries
- `primary_target.notes`: max 8192 chars
- `soft_targets`: list, max 64 entries
- `soft_targets[].notes`: max 2048 chars
- `coordinates.latitude`: -90 to 90
- `coordinates.longitude`: -180 to 180
- `summary`: max 16384 chars
- **Unknown fields are rejected** (`extra="forbid"`)

**Response 201**
```json
{
  "id": "0d0f7c8a-1234-5678-90ab-cdef01234567",
  "case_id": "CASE-2026-0001",
  "user_id": "1a2b3c4d-5e6f-7890-abcd-ef0123456789",
  "organisation_id": "11111111-2222-3333-4444-555555555555",
  "creator": {
    "id": "1a2b3c4d-5e6f-7890-abcd-ef0123456789",
    "name": "Alice Investigator",
    "email": "alice@example.com",
    "organisation": {
      "id": "11111111-2222-3333-4444-555555555555",
      "name": "Acme Investigations Ltd."
    }
  },
  "version": 1,
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "data": { /* full payload echoed back */ }
}
```

`creator` is a small embedded block (id, name, email, organisation) so admin and org-owner views don't have to cross-reference users to know who sent each report. `user_id` is kept alongside it for backwards compatibility — both point at the same user. `organisation_id` is the report's tenant; it equals `creator.organisation.id` for org-scoped reports and is `null` for admin-created reports.

---

#### `GET /api/v1/reports`

List reports. Server-scoped: `user` sees only their own; `org_owner` sees every report in their organisation; `admin` sees every report.

**Query params**
- `limit` (1–200, default 50)
- `offset` (≥ 0, default 0)

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "case_id": "CASE-2026-0001",
      "user_id": "uuid",
      "creator": {
        "id": "uuid",
        "name": "Alice Investigator",
        "email": "alice@example.com"
      },
      "version": 1,
      "created_at": "2026-04-15T16:30:00Z",
      "updated_at": "2026-04-15T16:30:00Z"
    }
  ],
  "total": 42
}
```

List responses **omit** the full `data` payload for efficiency. Use `GET /api/v1/reports/{id}` to load it. The `creator` block is included on every item so admin list views can show "report by Alice" without a separate user fetch.

---

#### `GET /api/v1/reports/{report_id}`

Fetch a single report including its full payload.

**Response 200** — same shape as the `POST /api/v1/reports` response.

**Errors**
- `404` — report not found or soft-deleted
- `403` — caller cannot view this report (not the creator, not in the same organisation, and not an admin)

---

#### `PATCH /api/v1/reports/{report_id}`

Edit a report. Allowed for the report's creator, any `org_owner` in the report's organisation, and any admin. Same write semantics: a snapshot of the prior state is written to `report_versions`, a new PDF is generated at a new path, and `version` is incremented; the old PDF is never overwritten.

`PATCH /api/v1/admin/reports/{report_id}` is kept as an admin-only alias for cross-organisation edits — same shape, same behaviour.

**Request** (all fields optional, at least one expected)
```json
{
  "case_id": "CASE-2026-0001-REV",
  "payload": { /* full payload — see POST /reports */ }
}
```

If `payload` is omitted the existing data is kept. If `case_id` is omitted the existing case_id is kept.

**Response 200** — same shape as `POST /api/v1/reports`, with incremented `version`.

**Errors**
- `400` / `422` — invalid body
- `401` — missing or expired token
- `403` — caller cannot edit this report (not the creator, not the report's `org_owner`, and not an admin)
- `404` — report not found or soft-deleted

The audit log records `action="report.update"` with `details.via = "owner" | "org_owner" | "admin"` so admins can distinguish self-edits, org-scoped edits, and cross-org admin edits.

---

#### `DELETE /api/v1/reports/{report_id}`

Soft-delete a report. Allowed for the `org_owner` of the report's organisation and for admins. Plain users (`role=user`) get `403` — they cannot delete reports they created. The PDF on disk is **not** removed.

**Response** — `204 No Content`. Idempotent — calling twice on a row that no longer exists returns `404`.

**Errors**
- `403` — caller is `role=user`, or `role=org_owner` from a different organisation
- `404` — report not found or already deleted

`DELETE /api/v1/admin/reports/{report_id}` is kept as an admin-only alias.

---

#### `GET /api/v1/reports/draft`

Fetch the **current user's** in-progress draft. Each user has at most one draft. Use this for power-outage / browser-crash recovery: the frontend autosaves to this endpoint, then re-loads the draft on app boot.

**Response 200**
```json
{
  "payload": {
    "case_id": "CASE-2026-0001",
    "payload": {
      "primary_target": { "name": "Subject A", "imei_numbers": [] },
      "soft_targets": [],
      "summary": null
    }
  },
  "updated_at": "2026-04-17T10:15:32.481Z"
}
```

If no draft exists:
```json
{ "payload": null, "updated_at": null }
```

The `payload` shape is **whatever the frontend last PUT** — there is no schema validation on the contents. The recommended convention is to mirror the `POST /reports` request body (`{ case_id, payload }`) so promoting a draft to a real report is a copy-paste, but that's a frontend convention, not a server requirement.

---

#### `PUT /api/v1/reports/draft`

Replace the current user's draft. Idempotent — call as often as you like (debounced autosave is fine). The server stamps `updated_at`.

**Request**
```json
{
  "payload": {
    "case_id": "CASE-2026-0001",
    "payload": {
      "primary_target": { "name": "Subject A" }
    }
  }
}
```

`payload` may be any JSON object (including `{}`). Cap: **256 KB** of serialized JSON. Bodies over the cap return `413`.

**Response 200** — same shape as `GET /reports/draft`, with the saved payload echoed back and a fresh `updated_at`.

**Errors**
- `413` — draft body exceeds the size cap
- `422` — request body is not a valid JSON object under the `payload` key

---

#### `DELETE /api/v1/reports/draft`

Clear the current user's draft. Call this after the frontend successfully `POST`s the draft as a real report.

**Response** — 204 No Content. Idempotent — calling twice is fine.

---

#### `GET /api/v1/reports/{report_id}/pdf`

Download the report PDF. Users can download their own; admins can download any.

**Response** — `application/pdf` streamed with headers:
```
Content-Disposition: attachment; filename="CASE-2026-0001-v1.pdf"
X-Content-Type-Options: nosniff
```

---

### Admin — Users

**All endpoints in this section require the caller to have `role=admin`.**

#### `POST /api/v1/admin/users`

Create a new user account.

**Request**
```json
{
  "email": "newagent@example.com",
  "password": "at-least-twelve-chars-here",
  "name": "Alice Investigator",
  "role": "user"
}
```

- `password`: 12–128 characters
- `name`: 1–100 characters — display name shown in admin listings and `/auth/me`
- `role`: `"user"` or `"admin"`

**Response 201**
```json
{
  "id": "uuid",
  "email": "newagent@example.com",
  "name": "Alice Investigator",
  "role": "user",
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "deleted_at": null
}
```

**Errors**
- `409` — email already registered

---

#### `GET /api/v1/admin/users`

List active users.

**Query params**: `limit` (1–200, default 50), `offset` (default 0)

**Response 200**
```json
{
  "items": [ /* UserRead... */ ],
  "total": 3
}
```

---

#### `PATCH /api/v1/admin/users/{user_id}`

Update a user. All fields optional.

**Request**
```json
{
  "email": "renamed@example.com",
  "password": "new-password-12-chars",
  "name": "Alice Investigator",
  "role": "admin"
}
```

**Important**: changing a user's password **revokes all their existing refresh tokens**, forcing them to log in again.

**Response 200** — UserRead.

---

#### `DELETE /api/v1/admin/users/{user_id}`

Soft-delete a user. Revokes all their refresh tokens. You cannot delete your own account.

**Response** — 204 No Content.

**Errors**
- `403` — attempting to delete yourself

---

### Admin — Organisations

**All endpoints in this section require the caller to have `role=admin`.** Non-admins get `401`/`403`. See **UPDATE.md** for the design rationale and the full visibility matrix.

#### `POST /api/v1/admin/organisations`

Create an organisation **and** its owner account in a single transaction. There is no two-step path — every organisation always has exactly one owner.

**Request**
```json
{
  "name": "Acme Investigations Ltd.",
  "owner": {
    "email": "owner@acme.example",
    "password": "an-actual-strong-password",
    "name": "Alice Owner"
  }
}
```

**Validation**
- `name`: 1–120 chars, unique among non-deleted organisations
- `owner.email`: must not already be registered
- `owner.password`: 12–128 chars
- `owner.name`: 1–100 chars

**Response 201**
```json
{
  "id": "11111111-2222-3333-4444-555555555555",
  "name": "Acme Investigations Ltd.",
  "owner_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "created_at": "2026-05-05T12:00:00Z",
  "updated_at": "2026-05-05T12:00:00Z",
  "deleted_at": null
}
```

The owner can log in immediately at `POST /api/v1/auth/login` with the credentials supplied; their `role` will be `org_owner` and `/auth/me` will return the new organisation.

**Errors**
- `409` — organisation name already in use, or owner email already registered

---

#### `GET /api/v1/admin/organisations`

List organisations.

**Query params** — `limit` (1–200, default 50), `offset` (≥ 0), `include_deleted` (default `false`).

**Response 200**
```json
{
  "items": [ { /* OrganisationRead */ } ],
  "total": 7
}
```

---

#### `GET /api/v1/admin/organisations/{org_id}`

Fetch one organisation.

**Errors**
- `404` — not found or soft-deleted (use `?include_deleted=true` on the list endpoint to find soft-deleted orgs)

---

#### `PATCH /api/v1/admin/organisations/{org_id}`

Rename an organisation.

**Request**
```json
{ "name": "Acme (renamed)" }
```

**Errors**
- `409` — new name conflicts with another active organisation
- `404` — not found

---

#### `DELETE /api/v1/admin/organisations/{org_id}`

Soft-delete an organisation. The row is marked `deleted_at`; nothing is actually removed.

Side effects:
- All refresh tokens for users in that organisation are revoked.
- The next request from any member's existing access token returns `401 organisation deactivated` (the deps layer checks this on every request).

**Response** — `204 No Content`.

---

#### `POST /api/v1/admin/organisations/{org_id}/users`

Admin-side user creation in any organisation. The `organisation_id` from the path always wins over the body.

**Request** — same shape as `POST /api/v1/admin/users` (the body's `organisation_id` is overwritten by the path):
```json
{
  "email": "newuser@acme.example",
  "password": "strong-password",
  "name": "New User",
  "role": "user"
}
```

`role` may be `user` or `org_owner`. Setting `org_owner` here makes the user an owner-eligible member of the org but does **not** automatically replace the existing owner — only one owner per org is allowed and the partial unique index will reject a second one. Reserve `org_owner` here for the rare case of resurrecting a soft-deleted previous owner.

**Response 201** — `UserRead`.

---

#### `GET /api/v1/admin/organisations/{org_id}/users`

List users in any organisation. Same shape as `GET /api/v1/admin/users` filtered by `organisation_id`.

---

#### `GET /api/v1/admin/organisations/{org_id}/reports`

List reports in any organisation. Same shape as `GET /api/v1/reports`.

---

### Org owner — Self-service

These routes are scoped implicitly to the caller's own organisation. The path never carries an org id; the server reads the organisation from the caller's identity. Required role: `org_owner` (admins are also accepted but should normally use the `/admin/organisations/...` paths instead).

#### `GET /api/v1/org/me`

Return the caller's organisation. Mirrors the admin `GET /api/v1/admin/organisations/{id}` for the caller's own tenant.

**Response 200** — `OrganisationRead` (see admin section).

**Errors**
- `404` — caller has no organisation (e.g. an admin without a tenant called this route by mistake)

---

#### `POST /api/v1/org/users`

Create a member in the caller's own organisation. The role is forced to `user` and the organisation is forced to the caller's — the body has neither field.

**Request**
```json
{
  "email": "alice@acme.example",
  "password": "strong-password",
  "name": "Alice"
}
```

**Response 201** — `UserRead`. The `role` is always `user`.

**Errors**
- `403` — caller is not an `org_owner`
- `409` — email already registered

---

#### `GET /api/v1/org/users`

List members of the caller's own organisation.

**Query params** — `limit`, `offset`.

**Response 200** — `UserListRead` (see Admin — Users).

---

#### `GET /api/v1/org/users/{user_id}`

Fetch one member. Caller must be in the same organisation, or fetching themselves.

**Errors**
- `403` — user is not in the caller's organisation
- `404` — user not found

---

#### `PATCH /api/v1/org/users/{user_id}`

Edit a member of the caller's own organisation (or self). Cannot change role or organisation — both fields are absent from the request body.

**Request** (all optional, at least one)
```json
{
  "email": "alice2@acme.example",
  "password": "new-strong-password",
  "name": "Alice (Married name)"
}
```

**Response 200** — `UserRead`.

**Errors**
- `403` — user is not in the caller's organisation
- `409` — email collision

---

#### `DELETE /api/v1/org/users/{user_id}`

Soft-delete a member of the caller's own organisation. The owner cannot be deleted via this path — admin must soft-delete the entire organisation first.

**Errors**
- `403` — user is not in the caller's organisation, or user is the organisation owner, or attempting self-delete

---

#### `GET /api/v1/org/reports`

List **every** report in the caller's organisation, regardless of which member created it. Mirrors `GET /api/v1/admin/organisations/{id}/reports` for the caller's own org.

**Query params** — `limit`, `offset`. **Response 200** — `ReportListRead`.

---

### Admin — Reports

**All endpoints in this section require the caller to have `role=admin`.** Non-admins get `401`/`403`. These routes are kept as cross-organisation aliases — the equivalent action on a single report is also reachable via the user-facing `PATCH/DELETE /api/v1/reports/{id}`.

#### `PATCH /api/v1/admin/reports/{report_id}`

Edit any report (admin cross-user edit). Identical request/response shape and write semantics to `PATCH /api/v1/reports/{report_id}`. A snapshot of the prior state is written to `report_versions`, a new PDF is generated at a new path, and `version` is incremented. The old PDF is never overwritten.

**Request** (all fields optional)
```json
{
  "case_id": "CASE-2026-0001-REV",
  "payload": { /* full payload — see POST /reports */ }
}
```

If `payload` is omitted the existing data is kept. If `case_id` is omitted the existing case_id is kept.

**Response 200** — same shape as `POST /api/v1/reports`, with incremented `version`.

**Errors**
- `403` — caller is not an admin
- `404` — report not found

---

#### `DELETE /api/v1/admin/reports/{report_id}`

Soft-deletes the report (`deleted_at` is set). PDF files on disk are **not removed**.

**Response** — 204 No Content.

---

### Admin — Audit log

#### `GET /api/v1/admin/audit`

**Admin only.** List audit log entries, newest first.

**Query params**: `limit` (1–500, default 100), `offset` (default 0)

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "actor_id": "uuid-or-null",
      "action": "report.create",
      "resource_type": "report",
      "resource_id": "uuid",
      "details": { "case_id": "CASE-2026-0001" },
      "created_at": "2026-04-15T16:30:00Z"
    }
  ],
  "total": 1247
}
```

**Actions you'll see**: `user.create`, `user.update`, `user.delete`, `user.seed_admin`, `report.create`, `report.update`, `report.delete`, `report.download`.

---

## JavaScript / Next.js examples

### Minimal auth helper

```ts
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL!; // e.g. http://41.242.54.70:4382

type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export async function login(email: string, password: string): Promise<Tokens> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `login failed (${res.status})`);
  }
  return res.json();
}

export async function refreshTokens(refreshToken: string): Promise<Tokens> {
  const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error("refresh failed — require re-login");
  return res.json();
}
```

### Authenticated fetch wrapper with auto-refresh

```ts
// lib/apiClient.ts
import { refreshTokens } from "./api";
import { getTokens, saveTokens, clearTokens } from "./tokenStorage";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL!;

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const tokens = getTokens();
  if (!tokens) throw new Error("not authenticated");

  const doFetch = (accessToken: string) =>
    fetch(`${API_BASE}/api/v1${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...init.headers,
      },
    });

  let res = await doFetch(tokens.access_token);
  if (res.status === 401) {
    try {
      const fresh = await refreshTokens(tokens.refresh_token);
      saveTokens(fresh);
      res = await doFetch(fresh.access_token);
    } catch {
      clearTokens();
      throw new Error("session expired — please log in again");
    }
  }
  return res;
}
```

### Creating a report

```ts
const res = await apiFetch("/reports", {
  method: "POST",
  body: JSON.stringify({
    case_id: "CASE-2026-0001",
    payload: {
      primary_target: {
        name: "Subject A",
        imei_numbers: ["490154203237518"],
        phone_numbers: ["+15551234567"],
        location: "42 Example Street",
        coordinates: { latitude: 51.5074, longitude: -0.1278 },
        notes: null,
      },
      soft_targets: [],
      summary: null,
    },
  }),
});
if (!res.ok) {
  const err = await res.json();
  throw new Error(err.detail);
}
const report = await res.json();
```

### Listing reports with pagination

```ts
const res = await apiFetch("/reports?limit=25&offset=0");
const { items, total } = await res.json();
```

### Downloading a PDF

```ts
const res = await apiFetch(`/reports/${reportId}/pdf`);
if (!res.ok) throw new Error("download failed");
const blob = await res.blob();
const url = URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = `${caseId}-v${version}.pdf`;
a.click();
URL.revokeObjectURL(url);
```

---

## CORS

The backend reads `CORS_ALLOWED_ORIGINS` from env at boot. Your frontend origin must be in that list or the browser will block requests.

To add your frontend's origin, SSH into the VPS and edit `/etc/softtarget/softtarget.env`:

```
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.yourdomain.com
```

Then restart the service: `systemctl restart softtarget.service`.

Wildcards are rejected in production.

---

## Dates and timestamps

All timestamps are **ISO 8601 UTC strings** (e.g. `2026-04-15T16:30:00Z`). Parse with `new Date(timestamp)`.

UUIDs are returned as lowercase strings.

---

## Versioning

All endpoints live under `/api/v1`. Any breaking change will ship as `/api/v2`; `/api/v1` won't be silently broken.
