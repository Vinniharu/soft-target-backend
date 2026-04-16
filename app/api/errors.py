"""Global exception handlers.

Service-layer errors map to clean HTTP responses here so endpoints don't
need to know about HTTP status codes and database/service details never
leak into the response body.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.services.errors import (
    Conflict,
    InvalidCredentials,
    NotFound,
    PermissionDenied,
    ServiceError,
)

_log = get_logger(__name__)


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return _error(status.HTTP_404_NOT_FOUND, str(exc) or "not found")

    @app.exception_handler(PermissionDenied)
    async def _forbidden(_: Request, exc: PermissionDenied) -> JSONResponse:
        return _error(status.HTTP_403_FORBIDDEN, str(exc) or "forbidden")

    @app.exception_handler(InvalidCredentials)
    async def _unauth(_: Request, exc: InvalidCredentials) -> JSONResponse:
        return _error(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    @app.exception_handler(Conflict)
    async def _conflict(_: Request, exc: Conflict) -> JSONResponse:
        return _error(status.HTTP_409_CONFLICT, str(exc) or "conflict")

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        _log.error("unhandled service error", error_type=type(exc).__name__)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "invalid request", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _fallback(_: Request, exc: Exception) -> JSONResponse:
        _log.exception("unhandled exception", error_type=type(exc).__name__)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error")
