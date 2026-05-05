"""v1 APIRouter aggregator."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, drafts, org, reports

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
# Drafts are mounted before reports so /reports/drafts beats the
# /reports/{report_id} catch-all on path matching.
api_router.include_router(drafts.router)
api_router.include_router(reports.router)
api_router.include_router(org.router)
api_router.include_router(admin.router)
