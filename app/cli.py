"""Typer CLI — administrative subcommands.

Run via ``uv run softtarget <command>``. The CLI is kept thin and mostly
delegates to the same services the HTTP layer uses.
"""

from __future__ import annotations

import asyncio
import getpass
import secrets
import sys

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import build_engine, build_sessionmaker, dispose_engine
from app.models.user import UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.organisation_repo import OrganisationRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.report_repo import ReportRepository
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService

app = typer.Typer(help="Soft Target administrative CLI")
_log = get_logger("cli")


async def _create_admin(email: str, password: str, name: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_format=False)
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            service = UserService(
                users=UserRepository(session),
                refresh_tokens=RefreshTokenRepository(session),
                audit=AuditRepository(session),
                settings=settings,
            )
            user, created = await service.ensure_admin_seed(
                email=email, password=password, name=name
            )
            await session.commit()
        if created:
            typer.echo(f"admin created: {user.email} ({user.id})")
        else:
            typer.echo(
                f"admin already exists for {user.email}; no changes made"
            )
    finally:
        await dispose_engine(engine)


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(None, "--email", help="Admin email address"),
    password: str = typer.Option(
        None,
        "--password",
        help="Admin password (prompted if omitted)",
    ),
    name: str = typer.Option(None, "--name", help="Admin display name"),
) -> None:
    """Seed the first admin account interactively."""

    if not email:
        email = typer.prompt("Admin email").strip()
    if not name:
        name = typer.prompt("Admin display name").strip()
    if not name or len(name) > 100:
        typer.echo("name must be 1-100 characters", err=True)
        raise typer.Exit(code=2)
    if not password:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            typer.echo("passwords do not match", err=True)
            raise typer.Exit(code=2)
    if len(password) < 12:
        typer.echo("password must be at least 12 characters", err=True)
        raise typer.Exit(code=2)
    try:
        asyncio.run(_create_admin(email, password, name))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        sys.exit(1)


# ----------------------------------------------------------------------
# Convert existing user account into an organisation owner
# ----------------------------------------------------------------------


async def _convert_to_org(email: str, org_name: str) -> dict[str, object]:
    settings = get_settings()
    configure_logging(settings.log_level, json_format=False)
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            users = UserRepository(session)
            organisations = OrganisationRepository(session)
            reports = ReportRepository(session)
            audit = AuditRepository(session)

            user = await users.get_by_email(email)
            if user is None:
                raise RuntimeError(f"no active user with email {email!r}")

            if user.role == UserRole.org_owner and user.organisation_id is not None:
                # Idempotent no-op.
                return {
                    "status": "already_converted",
                    "user_id": str(user.id),
                    "organisation_id": str(user.organisation_id),
                }
            if user.role != UserRole.user:
                raise RuntimeError(
                    f"user {email!r} has role {user.role.value!r}; "
                    "only role=user accounts may be converted"
                )
            if user.organisation_id is not None:
                raise RuntimeError(
                    f"user {email!r} already belongs to organisation "
                    f"{user.organisation_id}; cannot convert"
                )

            prior_role = user.role.value
            org = await organisations.create(
                name=org_name, owner_user_id=user.id
            )
            user.role = UserRole.org_owner
            user.organisation_id = org.id
            await users.update(user)

            stamped = await reports.stamp_org_for_user(
                user_id=user.id, organisation_id=org.id
            )
            await audit.record(
                actor_id=None,
                action="org.convert",
                resource_type="organisation",
                resource_id=str(org.id),
                details={
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "prior_role": prior_role,
                    "reports_stamped": stamped,
                },
            )
            await session.commit()
            return {
                "status": "converted",
                "user_id": str(user.id),
                "organisation_id": str(org.id),
                "reports_stamped": stamped,
            }
    finally:
        await dispose_engine(engine)


@app.command("convert-to-org")
def convert_to_org(
    email: str = typer.Argument(..., help="Email of the user to promote"),
    name: str = typer.Option(
        ...,
        "--name",
        help="Name of the new organisation",
    ),
) -> None:
    """Promote an existing user account into an organisation owner.

    Creates an organisation with the given name, sets the user's role
    to ``org_owner``, links them to the new org, and stamps every
    existing report owned by that user with the org id. Idempotent: a
    second run for the same email is a no-op.
    """

    if not name.strip() or len(name) > 120:
        typer.echo("name must be 1-120 characters", err=True)
        raise typer.Exit(code=2)
    try:
        result = asyncio.run(_convert_to_org(email, name.strip()))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        sys.exit(1)

    if result["status"] == "already_converted":
        typer.echo(
            f"already converted: {email} owns organisation "
            f"{result['organisation_id']}"
        )
        return
    typer.echo(
        f"converted {email}: organisation_id={result['organisation_id']}, "
        f"reports_stamped={result['reports_stamped']}"
    )


# ----------------------------------------------------------------------
# Dev seed
# ----------------------------------------------------------------------


async def _seed_dev(
    admin_email: str, domain: str
) -> list[tuple[str, str, str]]:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError(
            f"APP_ENV is {settings.app_env!r}; seed-dev only runs when APP_ENV=development"
        )

    configure_logging(settings.log_level, json_format=False)
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    seeded: list[tuple[str, str, str]] = []

    async def upsert_user(
        email: str,
        name: str,
        role: UserRole,
        organisation_id: object,
        users: UserRepository,
    ) -> tuple[object, str]:
        password = secrets.token_urlsafe(16)
        existing = await users.get_by_email(email, include_deleted=True)
        if existing is None:
            user = await users.create(
                email=email,
                password_hash=hash_password(password),
                name=name,
                role=role,
                organisation_id=organisation_id,  # type: ignore[arg-type]
            )
        else:
            existing.password_hash = hash_password(password)
            existing.name = name
            existing.role = role
            existing.organisation_id = organisation_id  # type: ignore[assignment]
            existing.deleted_at = None
            user = await users.update(existing)
        return user.id, password

    async def upsert_org(
        name: str, owner_id: object, organisations: OrganisationRepository
    ) -> object:
        # No idempotent get-by-name; re-running seed-dev assumes a clean
        # DB. If the org already exists by partial-unique-name, the
        # IntegrityError is bubbled up via ConflictError.
        org = await organisations.create(
            name=name, owner_user_id=owner_id  # type: ignore[arg-type]
        )
        return org.id

    try:
        async with sessionmaker() as session:
            users = UserRepository(session)
            organisations = OrganisationRepository(session)

            admin_id, admin_pw = await upsert_user(
                admin_email, "Admin", UserRole.admin, None, users
            )
            seeded.append(("admin", admin_email, admin_pw))

            for letter in ("a", "b"):
                owner_email = f"owner-{letter}@{domain}"
                owner_id, owner_pw = await upsert_user(
                    owner_email,
                    f"Org {letter.upper()} Owner",
                    UserRole.org_owner,
                    None,
                    users,
                )
                org_id = await upsert_org(
                    f"Org {letter.upper()}", owner_id, organisations
                )
                # Re-fetch and link the owner to the org.
                owner = await users.get(owner_id)  # type: ignore[arg-type]
                owner.organisation_id = org_id  # type: ignore[assignment]
                await users.update(owner)
                seeded.append((f"org_owner ({letter.upper()})", owner_email, owner_pw))

                member_email = f"member-{letter}@{domain}"
                _, member_pw = await upsert_user(
                    member_email,
                    f"Org {letter.upper()} Member",
                    UserRole.user,
                    org_id,
                    users,
                )
                seeded.append((f"user ({letter.upper()})", member_email, member_pw))
            await session.commit()
    finally:
        await dispose_engine(engine)

    return seeded


@app.command("seed-dev")
def seed_dev(
    admin_email: str = typer.Option(
        "admin@example.dev", "--admin-email", help="Email for the seeded admin"
    ),
    domain: str = typer.Option(
        "example.dev", "--domain", help="Email domain for seeded accounts"
    ),
) -> None:
    """Dev-only: create an admin + two organisations (each with an owner +
    one member) with generated passwords.

    Refuses to run unless APP_ENV=development. Assumes a fresh DB —
    re-running against an existing seed will fail on the unique org
    name.
    """

    try:
        seeded = asyncio.run(_seed_dev(admin_email, domain))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        sys.exit(1)

    typer.echo("")
    typer.echo("Save these now — passwords are not recoverable:")
    typer.echo("")
    typer.echo(f"{'ROLE':<22}{'EMAIL':<40}PASSWORD")
    for role, email, password in seeded:
        typer.echo(f"{role:<22}{email:<40}{password}")


@app.command("version")
def version() -> None:
    """Print the application version."""

    from app import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
