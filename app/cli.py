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
from app.repositories.refresh_token_repo import RefreshTokenRepository
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


async def _seed_dev(
    admin_email: str, investigators: int, domain: str
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

    async def upsert(
        email: str, name: str, role: UserRole, users: UserRepository
    ) -> str:
        password = secrets.token_urlsafe(16)
        existing = await users.get_by_email(email, include_deleted=True)
        if existing is None:
            await users.create(
                email=email,
                password_hash=hash_password(password),
                name=name,
                role=role,
            )
        else:
            existing.password_hash = hash_password(password)
            existing.name = name
            existing.role = role
            existing.deleted_at = None
            await users.update(existing)
        return password

    try:
        async with sessionmaker() as session:
            users = UserRepository(session)
            admin_pw = await upsert(
                admin_email, "Admin", UserRole.admin, users
            )
            seeded.append(("admin", admin_email, admin_pw))
            for i in range(1, investigators + 1):
                email = f"investigator{i}@{domain}"
                pw = await upsert(
                    email, f"Investigator {i}", UserRole.user, users
                )
                seeded.append(("investigator", email, pw))
            await session.commit()
    finally:
        await dispose_engine(engine)

    return seeded


@app.command("seed-dev")
def seed_dev(
    admin_email: str = typer.Option(
        "admin@example.dev", "--admin-email", help="Email for the seeded admin"
    ),
    investigators: int = typer.Option(
        3, "--investigators", min=0, max=50, help="Number of investigator accounts"
    ),
    domain: str = typer.Option(
        "example.dev", "--domain", help="Email domain for investigator accounts"
    ),
) -> None:
    """Dev-only: create an admin + N investigators with generated passwords.

    Refuses to run unless APP_ENV=development. If an account already
    exists it is reset with a new password, reactivated, and assigned
    the target role. Credentials are printed once to stdout.
    """

    try:
        seeded = asyncio.run(_seed_dev(admin_email, investigators, domain))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        sys.exit(1)

    typer.echo("")
    typer.echo("Save these now — passwords are not recoverable:")
    typer.echo("")
    typer.echo(f"{'ROLE':<14}{'EMAIL':<40}PASSWORD")
    for role, email, password in seeded:
        typer.echo(f"{role:<14}{email:<40}{password}")


@app.command("version")
def version() -> None:
    """Print the application version."""

    from app import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
