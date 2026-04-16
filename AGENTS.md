# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Cursor, Aider, etc.) when working with this repository. Read it in full before making any changes.

---

## Project Overview

**Soft Target Backend** is a FastAPI service that powers a confidential investigation report management platform. It pairs with a Next.js frontend (separate repo) that handles report creation UI and PDF/PNG export.

The system manages reports about investigation "targets". Each report contains:
- A primary target (IMEI numbers, phone numbers, location, coordinates)
- A list of associated "soft targets" (phone, location, lat/lng)
- Metadata (case ID, creator, timestamps)

Reports are confidential. Each one is tied to its creator and the audience is strictly controlled.

### Roles

- **User** — Authenticated investigators. Can create reports, view their own reports, and download them as PDF/PNG. **Cannot edit or delete reports.**
- **Admin** — Can do everything a user can, plus: create and manage user accounts, edit any report, delete (soft-delete) reports, and view audit logs.

There is **no public signup**. All accounts are created by an admin. The first admin is seeded via a CLI subcommand.

---

## Tech Stack

- **Python** 3.12+
- **FastAPI** — web framework
- **Uvicorn** — ASGI server (dev); **Gunicorn + Uvicorn workers** in production
- **PostgreSQL** 16+
- **SQLAlchemy 2.0** (async) — ORM / data mapper
- **asyncpg** — Postgres driver
- **Alembic** — migrations
- **Pydantic v2** — request/response schemas, validation
- **pydantic-settings** — env-driven config
- **python-jose[cryptography]** — JWT encode/decode
- **passlib[bcrypt]** — password hashing
- **WeasyPrint** — server-side HTML → PDF rendering
- **Jinja2** — HTML templates for PDF rendering
- **structlog** — structured logging
- **Typer** — CLI subcommands (`create-admin`, etc.)
- **pytest** + **pytest-asyncio** + **httpx** — testing
- **uv** — dependency / virtualenv management
- **ruff** — linting and formatting (replaces black, isort, flake8)
- **mypy** — static type checking

Avoid adding dependencies without explicit justification. Standard library first.

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory + startup/shutdown
│   ├── cli.py                   # Typer CLI (create-admin, etc.)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py              # Shared FastAPI dependencies (auth, db, etc.)
│   │   ├── errors.py            # Exception handlers + error responses
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py        # APIRouter aggregator
│   │       └── endpoints/
│   │           ├── auth.py      # /auth/login, /auth/refresh, /auth/me
│   │           ├── reports.py   # user-facing: create + read own + PDF
│   │           └── admin.py     # admin-only: user CRUD, audit, report edit/delete
│   ├── core/
│   │   ├── config.py            # pydantic-settings Settings class
│   │   ├── security.py          # JWT + bcrypt helpers
│   │   ├── logging.py           # structlog setup
│   │   └── rate_limit.py        # login rate limiting
│   ├── db/
│   │   ├── base.py              # DeclarativeBase
│   │   ├── session.py           # async engine + session factory
│   │   └── types.py             # custom column types (e.g. UUID)
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── report.py
│   │   ├── report_version.py
│   │   ├── refresh_token.py
│   │   └── audit_log.py
│   ├── schemas/                 # Pydantic DTOs (request/response)
│   │   ├── user.py
│   │   ├── report.py
│   │   ├── token.py
│   │   └── audit.py
│   ├── repositories/            # Data access (one per aggregate)
│   │   ├── errors.py            # NotFoundError, ConflictError
│   │   ├── user_repo.py
│   │   ├── report_repo.py
│   │   └── audit_repo.py
│   ├── services/                # Business logic + authorization
│   │   ├── user_service.py
│   │   ├── report_service.py
│   │   └── pdf_service.py       # WeasyPrint + Jinja2 PDF generation
│   ├── storage/
│   │   └── filestore.py         # local disk file storage for PDFs
│   └── templates/
│       └── report.html.j2       # Jinja2 template for PDF render
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                # migration files (append-only)
├── tests/
│   ├── conftest.py              # fixtures: app, client, db, factories
│   ├── unit/
│   └── integration/
├── scripts/
│   ├── deploy.sh
│   ├── gunicorn.conf.py
│   └── systemd/softtarget.service
├── .env.example
├── alembic.ini
├── pyproject.toml               # deps + tool config (ruff, mypy, pytest)
├── uv.lock
└── AGENTS.md
```

Treat anything under `app/` as the application package. Don't import from `tests/` into `app/`.

---

## Setup & Common Commands

This project uses **uv** for dependency and environment management.

```bash
# First-time setup
cp .env.example .env             # then edit values
uv sync                          # create venv + install deps
uv run alembic upgrade head      # apply migrations
uv run softtarget create-admin   # interactive prompt to seed first admin

# Daily development
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                    # all tests
uv run pytest tests/unit         # unit tests only
uv run pytest -m integration     # integration tests (requires DB)
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy app                  # type check

# Database
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic revision --autogenerate -m "add something"
uv run alembic revision -m "manual change"   # blank migration

# Build / package
uv build                         # produces wheel in dist/
```

A `Makefile` wraps the most common commands for muscle memory:

```bash
make dev          # uvicorn with --reload
make test
make lint         # ruff check + mypy
make fmt          # ruff format
make migrate
make migration name="..."
make create-admin
```

Always run `make fmt && make lint && make test` before considering a change complete.

---

## Code Conventions

### General

- **Format and lint with ruff.** Configuration lives in `pyproject.toml` under `[tool.ruff]`.
- **Type hints are required** on every function signature. `mypy --strict` for `app/`.
- **No bare `except:`.** Catch the narrowest exception you can.
- **No `print()` in `app/`.** Use the configured `structlog` logger.
- **Async all the way down.** All I/O (DB, HTTP, file) goes through async APIs. Don't mix sync DB calls into async paths.
- **No global mutable state** except the configured logger and the FastAPI app instance.
- Use `pathlib.Path` for filesystem paths, not string concatenation.

### FastAPI Endpoints

Endpoints stay **thin**. They only:
1. Validate input via Pydantic schemas
2. Resolve dependencies (auth, db session, current user)
3. Call into a service
4. Return a Pydantic response model

Business logic and authorization decisions belong in services. Endpoints should be 5–15 lines each.

```python
# app/api/v1/endpoints/reports.py
@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ReportRead:
    return await service.get_for_user(report_id, current_user)
```

Use `response_model=` on every endpoint that returns data — never let SQLAlchemy models leak out.

### Pydantic Schemas

- Request DTOs end in `Create` or `Update` (e.g. `ReportCreate`).
- Response DTOs end in `Read` (e.g. `ReportRead`).
- Internal DTOs (between service and repo) end in `Data`.
- Use `model_config = ConfigDict(from_attributes=True)` for response models built from ORM rows.
- Never reuse a schema for both request and response.

### Services

- One service per domain concept (`UserService`, `ReportService`, `PDFService`).
- Services receive a database session (and any other deps) via constructor injection.
- Services own authorization ("can this caller view this report?"), not endpoints, not middleware.
- Services raise typed exceptions (`PermissionDenied`, `NotFound`) — the global exception handler maps them to HTTP responses.

### Repositories

- One repo per aggregate root. Repos take an `AsyncSession` in `__init__`.
- Use SQLAlchemy 2.0 style: `select(...)`, `await session.execute(...)`, `result.scalars().first()`.
- Repos return ORM model instances or raise `NotFoundError`. They do **not** raise HTTP exceptions.
- Don't put business logic in repos — only data shaping and queries.

### Naming

- `snake_case` for functions, variables, modules.
- `PascalCase` for classes (including Pydantic schemas and SQLAlchemy models).
- `UPPER_SNAKE` for constants.
- Acronyms in identifiers stay lowercase: `user_id` (not `userId`), `imei`, `pdf_path`. Class names with acronyms keep them uppercase: `JWTError`.
- Test files: `test_*.py`. Test functions: `test_*`.

---

## Authentication & Authorization

- **JWT access tokens** — HS256, 15-minute lifetime, claims: `sub` (user ID as string), `role`, `exp`, `iat`, `jti`.
- **Refresh tokens** — random 32-byte URL-safe values stored as bcrypt hashes in `refresh_tokens`, 30-day lifetime, **single-use** (rotated on every refresh).
- The `get_current_user` dependency parses `Authorization: Bearer <token>` and loads the user. Use it on any endpoint that requires auth.
- Use `get_current_admin` (or a `RequireRole("admin")` dependency factory) on admin-only routes.
- **Resource-level checks** (e.g. "is this user the owner of this report?") happen in the **service layer**, never in dependencies or middleware.

The login endpoint is **rate-limited** (5 attempts per 15 minutes per IP, configurable). The limiter is in-memory and process-local; if you ever scale to multiple workers, swap for a Redis-backed implementation.

Never put secrets, tokens, or passwords into log lines, exception messages, or response bodies.

---

## Reports — Storage Model

Reports are stored **two ways**:

1. **Structured data in PostgreSQL** — for listing, filtering, search, and admin edits.
2. **Immutable PDF files on disk** — generated server-side at creation time and served on download. No regeneration on read.

### PDF generation

- Server generates the PDF via **WeasyPrint** rendering a **Jinja2** template (`app/templates/report.html.j2`).
- The template is the canonical layout. The frontend's preview render is for UX only — the downloaded PDF always comes from the server.
- PDFs live at `${STORAGE_DIR}/reports/<report-uuid>.v<version>.pdf`. The DB row holds the current relative path and version number.

### Edits (admin only)

- A new PDF is generated and stored at a new path with an incremented version.
- The old PDF is **kept on disk** — never overwritten.
- A row is inserted into `report_versions` with the prior data snapshot and PDF path.
- An audit log entry records who edited what.

### Deletes (admin only)

- DB row is **soft-deleted** (`deleted_at` set).
- PDF files are **not removed** from disk. Disk cleanup is a manual operator task.
- An audit log entry is written.

This is appropriate for confidential investigation work: nothing is silently destroyed, every change is traceable.

---

## Database

- Migrations are **append-only**. Never edit a committed migration — write a new one.
- UUIDs for primary keys (`gen_random_uuid()` from `pgcrypto`).
- Every table has `created_at`, `updated_at` (handled by SQLAlchemy `Mapped` defaults / `onupdate`). Soft-deletable tables also have `deleted_at`.
- Foreign keys are enforced. Use `ondelete="RESTRICT"` for `user → report` (we soft-delete users too).
- Index any column you filter, join, or sort on. Don't pre-optimize beyond that.
- Use `--autogenerate` for Alembic migrations when changing models, but **always review the generated SQL** before committing.

### Schema overview

```
users           (id, email, password_hash, role, created_at, updated_at, deleted_at)
reports         (id, case_id, user_id, data jsonb, pdf_path, version, created_at, updated_at, deleted_at)
report_versions (id, report_id, data jsonb, pdf_path, edited_by, edited_at)
refresh_tokens  (id, user_id, token_hash, expires_at, used_at)
audit_logs      (id, actor_id, action, resource_type, resource_id, details jsonb, created_at)
```

---

## Security

This is a confidential investigation tool. Security is first-class.

- **Never log** request bodies, response bodies, JWT contents, or report field values. Log only IDs, status codes, durations, and error categories. `structlog` processors should redact known sensitive keys.
- **Never include** report data in error messages returned to the client. Use generic messages and log details server-side.
- All endpoints require auth except `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, and `GET /healthz`.
- Set security headers on every response via middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `Strict-Transport-Security` in production.
- CORS is per-environment via env var. Default to deny. Never `*` in production.
- Validate all input through Pydantic schemas — never `dict`-typed bodies.
- File downloads: stream from disk via `StreamingResponse` with `aiofiles`. Never load a full PDF into memory.
- File paths: **never** trust a client-supplied path. Look up the row by ID and use the server-stored path. Reject any resolved path that escapes `STORAGE_DIR`.
- Passwords: bcrypt cost 12 minimum. Use `passlib`'s `CryptContext`.
- `JWT_SECRET` must be at least 32 bytes; the app refuses to start otherwise.
- Disable FastAPI's interactive docs (`/docs`, `/redoc`) in production via env flag.

---

## Testing

- Unit tests live in `tests/unit/`. Integration tests in `tests/integration/` and are marked with `@pytest.mark.integration`.
- Integration tests use a real Postgres (spun up via `docker-compose.test.yml`) and run inside transactions that roll back per test.
- Use `httpx.AsyncClient` with FastAPI's `ASGITransport` for endpoint tests — never start a real server.
- Coverage priorities (in order): services, repositories, auth dependencies, endpoint smoke tests.
- Use **parametrized tests** (`@pytest.mark.parametrize`) for anything with multiple cases.
- Don't test private implementation details — test behavior through the smallest public surface that reaches it.
- Factories for test data live in `tests/factories.py`. Prefer them over inline dict construction.

---

## Configuration

All config is loaded from environment variables at startup via `app/core/config.py` (a `pydantic_settings.BaseSettings` subclass). See `.env.example` for the full list. Required:

```
APP_ENV=production|development
HTTP_HOST=0.0.0.0
HTTP_PORT=8000
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/softtarget
JWT_SECRET=<32+ random bytes, base64-encoded>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=30
STORAGE_DIR=/var/lib/softtarget
CORS_ALLOWED_ORIGINS=https://app.example.com
LOG_LEVEL=info
ENABLE_DOCS=false
```

The app refuses to start if any required var is missing or invalid (Pydantic validation runs at boot).

---

## Deployment

Production target: a Linux VPS (Ubuntu 22.04 or 24.04) running:

- The FastAPI app under **Gunicorn with Uvicorn workers**, managed by **systemd** (`scripts/systemd/softtarget.service`)
- **Nginx** reverse proxy in front, with TLS via certbot
- **PostgreSQL 16** on the same host (or a managed instance)
- File storage on local disk under `/var/lib/softtarget` — **this directory must be backed up**
- WeasyPrint system dependencies installed: `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz0b` (see `scripts/deploy.sh` for the full apt list)

Deploy with `scripts/deploy.sh`: it ships the source tree, runs `uv sync` on the host, applies migrations, and restarts the systemd unit.

The service runs as a non-root `softtarget` system user. The process has no special capabilities.

---

## When Making Changes

When you (an AI agent) modify this codebase:

1. **Read the relevant existing files first.** Match the patterns already in use.
2. **Run `make fmt && make lint && make test`** before considering a change complete.
3. **Add or update tests** for any non-trivial logic change.
4. **Add Alembic migrations** rather than editing existing ones. Always review autogenerated SQL.
5. **Update this AGENTS.md** if you change conventions, structure, or commands.
6. **Be conservative with new dependencies.** Justify any addition in the PR description.
7. **Don't catch bare exceptions** or swallow errors silently.
8. **Don't log sensitive data.** Re-read the Security section if unsure.
9. **Don't bypass the service layer** by calling repositories directly from endpoints.
10. **Don't add public signup** or any other route that lets non-admins create accounts.
11. **Don't allow regular users to edit or delete reports** — that's an admin-only capability by design.
12. **Don't return database errors or stack traces** to the client. Map exceptions to clean HTTP responses.
13. **Don't mix sync I/O into async paths.** No `requests`, no sync SQLAlchemy calls — use `httpx` and async sessions.

---

## Out of Scope (Don't Add Without Explicit Discussion)

- A different ORM or query builder (we use SQLAlchemy 2.0 deliberately)
- GraphQL (REST only)
- Microservices / message queues / Celery
- User-facing password reset flow (admin handles password resets manually)
- Public API or API keys for third parties
- Multi-tenancy
- Real-time features (websockets, SSE)
- Any analytics or telemetry that ships report data off the host
- Switching the PDF engine away from WeasyPrint without a measured reason
