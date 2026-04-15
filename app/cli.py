"""Typer CLI — administrative subcommands.

Run via ``uv run softtarget <command>``. The CLI is kept thin and mostly
delegates to the same services the HTTP layer uses.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import build_engine, build_sessionmaker, dispose_engine
from app.repositories.audit_repo import AuditRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService

app = typer.Typer(help="Soft Target administrative CLI")
_log = get_logger("cli")


async def _create_admin(email: str, password: str) -> None:
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
                email=email, password=password
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
) -> None:
    """Seed the first admin account interactively."""

    if not email:
        email = typer.prompt("Admin email").strip()
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
        asyncio.run(_create_admin(email, password))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        sys.exit(1)


@app.command("version")
def version() -> None:
    """Print the application version."""

    from app import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
