# Update — New Endpoints

Quick reference for endpoints added or moved in the latest backend update. For full request/response shapes and validation rules, see `API.md`.

---

## New endpoints

### `GET /api/v1/auth/me`

Returns the currently-authenticated user. Use this on app boot to populate the user profile and verify the session.

**Auth:** `Authorization: Bearer <access_token>`

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

**Errors:** `401` if the token is missing, invalid, or expired.

---

### `GET /api/v1/reports/draft`

Load the current user's in-progress report draft. Returns nulls if no draft exists.

**Auth:** any authenticated user.

**Response 200**
```json
{
  "payload": { "case_id": "CASE-2026-0001", "payload": { /* … */ } },
  "updated_at": "2026-04-17T10:15:32.481Z"
}
```

When no draft exists:
```json
{ "payload": null, "updated_at": null }
```

---

### `PUT /api/v1/reports/draft`

Save (or autosave) the current user's draft. Replaces the existing draft. Idempotent.

**Auth:** any authenticated user.

**Request**
```json
{
  "payload": { /* any JSON object — frontend decides shape */ }
}
```

**Response 200** — same shape as `GET /reports/draft`, with the saved payload echoed and a fresh `updated_at`.

**Constraints**
- `payload` must be a JSON object (use `{}` if you need an empty draft).
- Cap: **256 KB** of serialized JSON.

**Errors**
- `413` — payload exceeds the size cap.
- `422` — body is not a valid JSON object under the `payload` key.

---

### `DELETE /api/v1/reports/draft`

Clear the current user's draft. Call this after a successful `POST /reports`. Idempotent.

**Auth:** any authenticated user.

**Response:** 204 No Content.

---

### `PATCH /api/v1/admin/reports/{report_id}`

**Moved** from `PATCH /api/v1/reports/{report_id}`. Edit a report — generates a new version + new PDF.

**Auth:** `role === "admin"`.

**Request** (all fields optional)
```json
{
  "case_id": "CASE-2026-0001-REV",
  "payload": { /* full payload — see POST /reports */ }
}
```

**Response 200** — same shape as `POST /reports`, with `version` incremented.

**Errors**
- `403` — caller is not an admin.
- `404` — report not found.

---

### `DELETE /api/v1/admin/reports/{report_id}`

**Moved** from `DELETE /api/v1/reports/{report_id}`. Soft-deletes the report. PDF files on disk are not removed.

**Auth:** `role === "admin"`.

**Response:** 204 No Content.

---

## Changed: existing endpoint response shape

### `POST /api/v1/auth/login` — adds `role`

The login response now includes the user's role so the frontend can route to the right landing page without a follow-up call.

**Response 200**
```json
{
  "access_token": "…",
  "refresh_token": "…",
  "token_type": "bearer",
  "expires_in": 900,
  "role": "user"
}
```

`role` is `"user"` or `"admin"`.

---

## Quick endpoint matrix

### Public (no auth)
- `POST /api/v1/auth/login` — rate-limited (5 / 15 min / IP)
- `POST /api/v1/auth/refresh`

### Authenticated (any role)
- `GET /api/v1/auth/me` *(new)*
- `POST /api/v1/reports`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{id}`
- `GET /api/v1/reports/{id}/pdf`
- `GET /api/v1/reports/draft` *(new)*
- `PUT /api/v1/reports/draft` *(new)*
- `DELETE /api/v1/reports/draft` *(new)*

### Admin only (`role === "admin"`)
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{id}`
- `DELETE /api/v1/admin/users/{id}`
- `PATCH /api/v1/admin/reports/{id}` *(moved here from `/reports/{id}`)*
- `DELETE /api/v1/admin/reports/{id}` *(moved here from `/reports/{id}`)*
- `GET /api/v1/admin/audit`
