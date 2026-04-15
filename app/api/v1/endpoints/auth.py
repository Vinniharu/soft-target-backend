"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import client_ip, get_login_rate_limiter, get_user_service
from app.core.logging import get_logger
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.token import LoginCreate, RefreshCreate, TokenPair
from app.services.errors import RateLimited
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])
_log = get_logger(__name__)


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    payload: LoginCreate,
    service: Annotated[UserService, Depends(get_user_service)],
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_login_rate_limiter)],
) -> TokenPair:
    ip = client_ip(request)
    if not await limiter.check_and_record(f"login:{ip}"):
        _log.warning("login rate limited", ip=ip)
        raise RateLimited("too many login attempts")

    user = await service.authenticate(email=payload.email, password=payload.password)
    tokens = await service.issue_tokens(user)
    _log.info("login success", user_id=str(user.id), ip=ip)
    return tokens


@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def refresh(
    payload: RefreshCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> TokenPair:
    return await service.refresh(refresh_token=payload.refresh_token)
