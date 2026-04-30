"""FastAPI application factory, lifespan, and wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestLogMiddleware, SecurityHeadersMiddleware
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.session import build_engine, build_sessionmaker, dispose_engine
from app.services.pdf_service import PDFService
from app.storage.filestore import FileStore


def _validate_production_settings(settings: Settings) -> None:
    if settings.is_production:
        if "*" in settings.cors_origins:
            raise RuntimeError("CORS wildcard is not permitted in production")
        if not settings.cors_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log = get_logger(__name__)
    log.info(
        "startup",
        app_env=settings.app_env,
        storage_dir=str(settings.storage_dir),
    )

    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)

    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    filestore = FileStore(settings.storage_dir)
    pdf_service = PDFService()

    login_rate_limiter = SlidingWindowRateLimiter(
        max_attempts=settings.login_rate_limit_max_attempts,
        window_seconds=settings.login_rate_limit_window_minutes * 60,
    )

    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.filestore = filestore
    app.state.pdf_service = pdf_service
    app.state.login_rate_limiter = login_rate_limiter

    try:
        yield
    finally:
        log.info("shutdown")
        await dispose_engine(engine)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _validate_production_settings(settings)
    configure_logging(settings.log_level, json_format=settings.is_production)

    app = FastAPI(
        title="Soft Target Backend",
        version="0.1.0",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware, is_production=settings.is_production
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
