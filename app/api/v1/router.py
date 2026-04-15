"""v1 APIRouter aggregator."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, reports

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
