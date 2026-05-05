# Soft Target — Organisation Restructure

This document is the frontend handoff for the move from a 2-tier permission model (admin + users) to a 3-tier tenant model (admin → organisation → users-within-organisation). Every backend change required for this restructure is now in `main`.

For the canonical request/response shape of every endpoint, see **API.md**. This file is the *narrative* of what changed and why.

---

## 1. Overview

### Why

Originally the backend had a single admin who created bare user accounts; each user owned reports they created. In practice, each of the two production accounts on the system has been used by an entire company. Two consequences:

- Inside a company there's only ever been one set of credentials — no per-investigator audit trail.
- A company has no way to add or remove its own staff without going through admin.

The new model fixes both. Companies become **organisations**. Each organisation has one **org owner** and zero or more **users** under it. The org owner can self-serve add / remove / edit their staff and sees every report any of their staff created.

### Roles

| Role | Authority |
|---|---|
| `user` | Belongs to one organisation. Can create reports; can view, edit, and download reports they created. **Cannot delete reports.** Cannot see other users' reports — even from the same organisation. |
| `org_owner` | Belongs to one organisation; exactly one per organisation. Everything a `user` can do, plus: see / edit / **delete** every report in the organisation. Create / edit / soft-delete users in the organisation. Cannot see anything outside the organisation. |
| `admin` | Belongs to no organisation. Creates and manages organisations. Can edit / delete reports anywhere. Can manage users in any organisation. Sees audit logs. |

### Tenant rules in one paragraph

A user belongs to at most one organisation (admins belong to none). A report is stamped with the creator's organisation at write time and stays attributed to that organisation for life — even if the user later changes orgs (out of scope for this release; just noting the durability). Visibility uses three lenses: admins see everything; org owners see everything inside their org; users see only what they created.

---

## 2. Authentication & Identity

### What didn't change

- `POST /api/v1/auth/login` — same request body, same response shape. Still returns `access_token`, `refresh_token`, `expires_in`, `role`. The `role` field can now also be `"org_owner"` in addition to `"user"` and `"admin"`.
- `POST /api/v1/auth/refresh` — same.
- Refresh token rotation, single-use, 30-day expiry — same.

### What changed

`GET /api/v1/auth/me` now includes an `organisation` block:

```json
{
  "id": "1a2b3c4d-...",
  "email": "alice@acme.example",
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

`organisation` is `null` for admin accounts (admins do not belong to any tenant). For `org_owner` and `user` it is always populated.

> **Frontend recommendation:** call `/auth/me` once after login and stash `{ id, role, organisation }` into your auth store. All UI gating (which menu items to show, which pages to route to) should read from there. Don't try to encode the role on the URL.

### Org soft-delete: how it shows up

If admin soft-deletes the organisation that the caller belongs to, the next request from that caller's existing access token returns `401 organisation deactivated`. Refresh tokens are also revoked, so the user cannot recover by hitting `/auth/refresh`. The frontend should treat this exactly like any other `401` — clear local auth state and redirect to login. (At login they will get `401 invalid email or password` because the user-active check rejects them.)

---

## 3. Organisations (admin-only)

These routes are gated to `role=admin`. Non-admins get `401`/`403`.

### Create — atomic owner included

`POST /api/v1/admin/organisations`

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

The organisation and its owner account are created in the same transaction. There is no two-step "create org, then add owner" flow — every organisation always has exactly one owner.

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

The owner can log in immediately at `POST /api/v1/auth/login`; their `role` will be `org_owner` and `/auth/me` will include the new organisation.

### Read

- `GET /api/v1/admin/organisations` — list (`limit`, `offset`, `include_deleted`)
- `GET /api/v1/admin/organisations/{id}` — single
- `GET /api/v1/admin/organisations/{id}/users` — every user in the org
- `GET /api/v1/admin/organisations/{id}/reports` — every report in the org

### Modify

- `PATCH /api/v1/admin/organisations/{id}` — body `{ "name": "..." }`. Renames only.
- `DELETE /api/v1/admin/organisations/{id}` — soft-delete. Cascades: every member of the org gets their refresh tokens revoked and will be `401`'d on their next request.

### Admin creating a user inside any organisation

`POST /api/v1/admin/organisations/{org_id}/users`

```json
{
  "email": "newuser@acme.example",
  "password": "strong-password",
  "name": "New User",
  "role": "user"
}
```

The path's `org_id` always wins over the body's `organisation_id`. Setting `role` to `org_owner` here is allowed (and will conflict with the existing owner via the partial unique index — only one owner per org), but in practice you almost always want `role=user`.

---

## 4. User management — by role

There are now two paths that create / edit / delete users. They differ in scope and in what the request body accepts.

| Path | Caller | Scope | Role assignment |
|---|---|---|---|
| `/api/v1/admin/users` and `/api/v1/admin/organisations/{id}/users` | admin only | any user, any org | request body chooses; admin can assign any role |
| `/api/v1/org/users` | org_owner | own organisation only | role is **forced** to `user` server-side; body has no role field |

### Org-owner endpoints — the everyday path

These routes do not include the org id in the URL. The server reads it from the caller's identity.

```
GET    /api/v1/org/me                    own organisation details
GET    /api/v1/org/users                  list members of own org
POST   /api/v1/org/users                  create a member (role forced to "user")
GET    /api/v1/org/users/{id}             get one member
PATCH  /api/v1/org/users/{id}             edit a member
DELETE /api/v1/org/users/{id}             soft-delete a member
GET    /api/v1/org/reports                list every report in own org
```

`POST /api/v1/org/users` body has only `{ email, password, name }`. Any `role` or `organisation_id` field would be a client bug — the server forces both.

`PATCH /api/v1/org/users/{id}` body has `{ email?, password?, name? }`. Org owners can edit themselves and any member of their organisation. They **cannot** change role or organisation through this path.

`DELETE /api/v1/org/users/{id}` soft-deletes a member. Constraints: cannot delete yourself, cannot delete the organisation owner. To remove an organisation owner, admin must soft-delete the entire organisation.

### Self-edit — what each role can change about themselves

- `user`: nothing yet (no self-edit endpoint exists). Members ask their org owner to update them.
- `org_owner`: hits `PATCH /api/v1/org/users/{ownId}` to change own email / password / name. Cannot change own role or organisation.
- `admin`: hits `PATCH /api/v1/admin/users/{ownId}` to change anything. Cannot self-delete (self-delete is blocked by service).

### Role escalation guard

If anybody other than `admin` tries to assign `role=admin` or `role=org_owner` (e.g. by hitting `/admin/users` while authenticated as an org owner), they get `403`. Org owners can only ever create `role=user` accounts. All role-assignment decisions happen server-side; the frontend should treat the role field as read-only for org owners.

---

## 5. Reports — visibility matrix

### Per-action breakdown

| Action | `user` | `org_owner` | `admin` |
|---|---|---|---|
| `POST /api/v1/reports` (create) | ✓ — stamps own org | ✓ — stamps own org | ✓ — stamps no org (admin-created reports are org-less) |
| `GET /api/v1/reports` (list) | only own | every report in own org | every report |
| `GET /api/v1/reports/{id}` | only if creator | any in own org | any |
| `GET /api/v1/reports/{id}/pdf` | only if creator | any in own org | any |
| `PATCH /api/v1/reports/{id}` | only if creator | any in own org | any |
| `DELETE /api/v1/reports/{id}` | **403** — users cannot delete | any in own org | any |
| `PATCH /api/v1/admin/reports/{id}` | 403 | 403 | any (admin-only alias) |
| `DELETE /api/v1/admin/reports/{id}` | 403 | 403 | any (admin-only alias) |

### `creator` block — now includes organisation

Every report response (single or in a list) includes a `creator` block. After this release the block has an `organisation` field:

```json
"creator": {
  "id": "1a2b3c4d-...",
  "name": "Alice Investigator",
  "email": "alice@acme.example",
  "organisation": {
    "id": "11111111-2222-3333-4444-555555555555",
    "name": "Acme Investigations Ltd."
  }
}
```

`organisation` is `null` for admin-created reports (admins have no tenant), populated otherwise. Use this in admin tables to render "report by Alice (Acme)" without a separate user lookup.

The top-level report payload also gains `organisation_id: uuid | null` for convenience — equal to `creator.organisation.id`, or null for admin-created reports.

### Admin-created reports

Admins can create reports — they have no organisation, so the resulting row has `organisation_id: null`. These reports are visible only to admins (org owners' filter `organisation_id = own_org` excludes them, and they have no creator-org match). Treat them as a private admin scratchpad. There's no UI bucket for "admin reports" by default; if you want one, filter the admin list view for `organisation_id == null`.

### New / changed routes

- `DELETE /api/v1/reports/{id}` — **new**. Soft-deletes a report. Allowed for `admin` and `org_owner` of the report's organisation. Plain `user` callers get `403`.
- `GET /api/v1/reports` — semantics changed: now scopes to the caller's role.
- `GET /api/v1/reports/{id}`, `PATCH /api/v1/reports/{id}` — semantics changed to include the org-owner branch.
- `PATCH /api/v1/admin/reports/{id}`, `DELETE /api/v1/admin/reports/{id}` — kept as admin-only aliases. No reason to use them from a frontend that already has the user-facing routes; keep them around for cross-org admin tooling.

---

## 6. Frontend wiring

### Routing / navigation

After login, branch by `role`:

```
admin     → /admin (admin dashboard with org list, audit log, etc.)
org_owner → /org   (org dashboard with member list and org-wide reports)
user      → /reports (own reports list + create)
```

Source the role from `/auth/me` (not from the JWT directly — the access token has `role` in claims but the server already round-trips the DB and may have changed it).

### Cached state

Stash the result of `/auth/me` in your auth store with a TTL (e.g. on every login + on every refresh). Read `organisation.name` from there for the header tag, `role` for menu gating, etc. Don't try to derive the org from the report list.

### Sidebar / menu items

| Item | `user` | `org_owner` | `admin` |
|---|---|---|---|
| My reports | ✓ | ✓ | ✓ |
| Create report | ✓ | ✓ | ✓ |
| Org reports | — | ✓ (`/org/reports`) | — (admins go through `/admin/organisations/{id}/reports`) |
| Manage members | — | ✓ (`/org/users`) | ✓ (under the org page) |
| Manage organisations | — | — | ✓ |
| Audit log | — | — | ✓ |

### Error handling

- `401 organisation deactivated` — clear auth state, redirect to login. (You won't be able to recover by refreshing.)
- `403` on `DELETE /reports/{id}` from a regular user — show a toast like "Only your organisation owner can delete reports."
- `403` on admin-only paths from an org owner — show "This action is admin-only."
- `409` on `POST /admin/organisations` — owner email already taken, or organisation name already taken. Surface the server message to the user.

### Forms

- The org-owner "create member" form has only `{ email, password, name }`. Don't render a role selector.
- The admin "create user" form can show a role selector. Default to `user`.
- The "create organisation" form needs `{ name, owner: { email, password, name } }`. Validate password length client-side (>=12) for fast feedback.

---

## 7. Migration & deployment

### Database

`alembic upgrade head` applies migration `0004_organisations`:

- Creates table `organisations(id, name, owner_user_id, created_at, updated_at, deleted_at)` with partial-unique indexes on `name` and `owner_user_id` (where `deleted_at IS NULL`).
- Adds `users.organisation_id` (nullable FK, ondelete RESTRICT, indexed).
- Adds `reports.organisation_id` (nullable FK, ondelete RESTRICT, partial index on `(organisation_id, created_at) WHERE deleted_at IS NULL`).

There is **no data backfill** in the migration. Existing rows keep `organisation_id = NULL`.

### Existing user accounts → organisations

The two existing user accounts that were being used as company accounts get promoted with the new CLI:

```
softtarget convert-to-org owner-a@example.dev --name "Org A"
softtarget convert-to-org owner-b@example.dev --name "Org B"
```

Per email, in one transaction:

1. Creates a new `Organisation(name=...)` with the user as the owner.
2. Sets the user's `role = org_owner` and links them to the new org.
3. Stamps every existing report owned by that user with the new `organisation_id`.
4. Records an `org.convert` audit log row.

The command is **idempotent**: running it a second time for the same email is a no-op (returns "already converted: ...").

After conversion, those accounts log in with the same credentials and get `role: "org_owner"` plus the new `organisation` block in `/auth/me`. Their existing reports are now visible to them via `/org/reports`.

### Deploy steps

```bash
# On the VPS
softtarget-deploy                                    # pull, install, alembic upgrade, restart
softtarget convert-to-org owner-a@example.dev --name "Org A"
softtarget convert-to-org owner-b@example.dev --name "Org B"
```

Verify by logging in to each converted account and checking that `/auth/me` now reports `role: "org_owner"` and a populated `organisation` block.

### Frontend impact summary

- New routes to wire up: `/api/v1/admin/organisations*`, `/api/v1/org/*`, `DELETE /api/v1/reports/{id}`.
- Updated semantics: `/api/v1/reports` GET / PATCH now scoped by role server-side; `/auth/me` and report responses gain organisation blocks.
- Compatibility: no breaking changes to existing routes — the flat `/admin/users` routes still work, login response shape is unchanged, report request bodies are unchanged.

---

## 8. Verification checklist

After deploy, run through these manually:

1. Log in as admin → `GET /admin/organisations` returns `Org A` and `Org B`.
2. Log in as `owner-a@…` → `role: "org_owner"`, `/auth/me` shows `Org A`.
3. As that owner: `POST /org/users` → creates a `user`-role member; `GET /org/users` lists them.
4. As that member: `POST /reports` → succeeds; `GET /reports` returns only their report.
5. Back as the owner: `GET /org/reports` returns the member's report **and** any of the owner's own reports.
6. As the member: `DELETE /reports/{ownReport}` → `403`. As the owner: `DELETE /reports/{anyOrgReport}` → `204`.
7. As `owner-a`: `GET /reports/{orgB_report}` → `403` (cross-org denied).
8. As admin: `DELETE /admin/organisations/{Org A id}` → `204`; next `/auth/me` from `owner-a`'s existing token → `401 organisation deactivated`.

If any of those return something other than the listed status, capture the failing response and check the audit log (`GET /api/v1/admin/audit`) for the surrounding actions.
