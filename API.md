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

| Role  | Can do |
|-------|--------|
| `user`  | Create reports, view/download their own reports |
| `admin` | Everything a user can do, plus: edit/delete any report, create/edit/delete users, view audit logs |

Users cannot edit or delete reports — that's admin-only by design.

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

`expires_in` is seconds until the access token expires (900 = 15 min). `role` is `"user"` or `"admin"` and lets the frontend pick the right post-login landing page without a follow-up call.

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
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "deleted_at": null
}
```

**Errors**
- `401` — missing, invalid, or expired access token

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
  "version": 1,
  "created_at": "2026-04-15T16:30:00Z",
  "updated_at": "2026-04-15T16:30:00Z",
  "data": { /* full payload echoed back */ }
}
```

---

#### `GET /api/v1/reports`

List reports. Users see only their own; admins see all.

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
      "version": 1,
      "created_at": "2026-04-15T16:30:00Z",
      "updated_at": "2026-04-15T16:30:00Z"
    }
  ],
  "total": 42
}
```

List responses **omit** the full `data` payload for efficiency. Use `GET /api/v1/reports/{id}` to load it.

---

#### `GET /api/v1/reports/{report_id}`

Fetch a single report including its full payload.

**Response 200** — same shape as the `POST /api/v1/reports` response.

**Errors**
- `404` — report not found or soft-deleted
- `403` — user trying to read someone else's report

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

### Admin — Reports

**All endpoints in this section require the caller to have `role=admin`.** Non-admins hitting these URLs get `401` (not authenticated) or `403` (wrong role); the write surface is not exposed to regular users.

#### `PATCH /api/v1/admin/reports/{report_id}`

Edit a report. A snapshot of the prior state is written to `report_versions`, a new PDF is generated at a new path, and `version` is incremented. The old PDF is never overwritten.

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
