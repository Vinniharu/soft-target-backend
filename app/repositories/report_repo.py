"""Report data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report import Report
from app.models.report_version import ReportVersion
from app.repositories.errors import NotFoundError


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        report_id: uuid.UUID,
        *,
        include_deleted: bool = False,
        with_creator: bool = False,
    ) -> Report:
        stmt = select(Report).where(Report.id == report_id)
        if with_creator:
            stmt = stmt.options(selectinload(Report.creator))
        if not include_deleted:
            stmt = stmt.where(Report.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        report = result.scalar_one_or_none()
        if report is None:
            raise NotFoundError(f"report {report_id} not found")
        return report

    async def create(
        self,
        *,
        case_id: str,
        user_id: uuid.UUID,
        data: dict[str, Any],
        pdf_path: str,
    ) -> Report:
        report = Report(
            case_id=case_id,
            user_id=user_id,
            data=data,
            pdf_path=pdf_path,
            version=1,
        )
        self._session.add(report)
        await self._session.flush()
        await self._session.refresh(report)
        return report

    async def set_pdf_path(self, report: Report, pdf_path: str) -> Report:
        report.pdf_path = pdf_path
        await self._session.flush()
        await self._session.refresh(report)
        return report

    async def replace_content(
        self,
        report: Report,
        *,
        case_id: str,
        data: dict[str, Any],
        pdf_path: str,
    ) -> Report:
        report.case_id = case_id
        report.data = data
        report.pdf_path = pdf_path
        report.version += 1
        await self._session.flush()
        await self._session.refresh(report)
        return report

    async def record_version(
        self,
        *,
        report_id: uuid.UUID,
        version: int,
        data: dict[str, Any],
        pdf_path: str,
        edited_by: uuid.UUID,
    ) -> ReportVersion:
        entry = ReportVersion(
            report_id=report_id,
            version=version,
            data=data,
            pdf_path=pdf_path,
            edited_by=edited_by,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def soft_delete(self, report: Report) -> None:
        report.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Report], int]:
        base = select(Report).where(
            Report.user_id == user_id, Report.deleted_at.is_(None)
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            base.options(selectinload(Report.creator))
            .order_by(Report.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[Report], int]:
        base = select(Report)
        if not include_deleted:
            base = base.where(Report.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            base.options(selectinload(Report.creator))
            .order_by(Report.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)
