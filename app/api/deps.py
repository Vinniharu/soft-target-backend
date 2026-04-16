"""Shared FastAPI dependencies.

Dependencies in this module focus on wiring: they grab the DB session
from the app state, build repositories, and hand them to services. All
business logic and authorization stay inside services.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import TokenError, decode_access_token
from app.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.errors import NotFoundError
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.report_repo import ReportRepository
from app.repositories.user_repo import UserRepository
from app.services.draft_service import DraftService
from app.services.pdf_service import PDFService
from app.services.report_service import ReportService
from app.services.user_service import UserService
from app.storage.filestore import FileStore

_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.sessionmaker  # type: ignore[no-any-return]


def get_filestore(request: Request) -> FileStore:
    return request.app.state.filestore  # type: ignore[no-any-return]


def get_pdf_service(request: Request) -> PDFService:
    return request.app.state.pdf_service  # type: ignore[no-any-return]


def get_login_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    return request.app.state.login_rate_limiter  # type: ignore[no-any-return]


async def get_session(
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_sessionmaker)
    ],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_report_repo(session: SessionDep) -> ReportRepository:
    return ReportRepository(session)


def get_audit_repo(session: SessionDep) -> AuditRepository:
    return AuditRepository(session)


def get_refresh_token_repo(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_user_service(
    settings: SettingsDep,
    users: Annotated[UserRepository, Depends(get_user_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repo)],
    audit: Annotated[AuditRepository, Depends(get_audit_repo)],
) -> UserService:
    return UserService(
        users=users,
        refresh_tokens=refresh_tokens,
        audit=audit,
        settings=settings,
    )


def get_report_service(
    reports: Annotated[ReportRepository, Depends(get_report_repo)],
    audit: Annotated[AuditRepository, Depends(get_audit_repo)],
    pdf: Annotated[PDFService, Depends(get_pdf_service)],
    filestore: Annotated[FileStore, Depends(get_filestore)],
) -> ReportService:
    return ReportService(
        reports=reports,
        audit=audit,
        pdf=pdf,
        filestore=filestore,
    )


def get_draft_service(
    users: Annotated[UserRepository, Depends(get_user_repo)],
) -> DraftService:
    return DraftService(users=users)


async def get_current_user(
    settings: SettingsDep,
    users: Annotated[UserRepository, Depends(get_user_repo)],
    token: Annotated[str | None, Depends(_bearer)],
) -> User:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(settings, token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        user_id = uuid.UUID(claims.sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        ) from exc

    try:
        user = await users.get(user_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user no longer exists",
        ) from exc

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user is deactivated",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class RequireRole:
    def __init__(self, role: UserRole) -> None:
        self._role = role

    async def __call__(self, user: CurrentUser) -> User:
        if self._role == UserRole.admin and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="admin role required",
            )
        return user


require_admin = RequireRole(UserRole.admin)
CurrentAdmin = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    """Best-effort client IP for logging and rate limiting.

    ``X-Forwarded-For`` is honored only when the immediate peer
    (``request.client.host``) is in ``TRUSTED_PROXIES``. Otherwise the
    header is ignored — any caller could otherwise spoof their IP, which
    would defeat IP-based rate limiting and pollute audit logs.
    """

    peer = request.client.host if request.client is not None else None
    settings: Settings = request.app.state.settings
    networks = settings.trusted_proxy_networks

    if peer is not None and networks:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            peer_ip = None
        if peer_ip is not None and any(peer_ip in net for net in networks):
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()

    if peer is not None:
        return peer
    return "unknown"
