"""Report business logic and authorization.

The service owns every "can this caller do X to this report?" decision.
Endpoints never touch repositories directly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.models.report import Report
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.errors import NotFoundError
from app.repositories.report_repo import ReportRepository
from app.schemas.report import ReportCreate, ReportPayload, ReportUpdate
from app.services.errors import NotFound, PermissionDenied
from app.services.pdf_service import PDFService
from app.storage.filestore import FileStore, FileStoreError


class ReportService:
    def __init__(
        self,
        *,
        reports: ReportRepository,
        audit: AuditRepository,
        pdf: PDFService,
        filestore: FileStore,
    ) -> None:
        self._reports = reports
        self._audit = audit
        self._pdf = pdf
        self._filestore = filestore

    async def create(
        self, *, payload: ReportCreate, creator: User
    ) -> Report:
        # Persist the DB row first so we have a UUID for the pdf path, then
        # render and update.
        report = await self._reports.create(
            case_id=payload.case_id,
            user_id=creator.id,
            data=payload.payload.model_dump(mode="json"),
            pdf_path="",
        )
        relpath = self._filestore.report_relpath(report.id, report.version)
        pdf_bytes = self._pdf.render_pdf(
            report_id=report.id,
            case_id=report.case_id,
            version=report.version,
            creator_email=creator.email,
            payload=payload.payload,
            created_at=report.created_at,
        )
        await self._filestore.write_bytes(relpath, pdf_bytes)
        report = await self._reports.set_pdf_path(report, relpath)
        # Pin the creator in-memory so the response shape (which embeds
        # ReportCreatorRead) doesn't trigger an async lazy-load on the
        # ORM relationship.
        report.creator = creator
        await self._audit.record(
            actor_id=creator.id,
            action="report.create",
            resource_type="report",
            resource_id=str(report.id),
            details={"case_id": report.case_id},
        )
        return report

    async def get_for_user(
        self, report_id: uuid.UUID, *, actor: User
    ) -> Report:
        try:
            report = await self._reports.get(report_id, with_creator=True)
        except NotFoundError as exc:
            raise NotFound("report not found") from exc
        self._authorize_read(report, actor)
        return report

    async def list_for_user(
        self, *, actor: User, limit: int, offset: int
    ) -> tuple[list[Report], int]:
        if actor.is_admin:
            return await self._reports.list_all(limit=limit, offset=offset)
        return await self._reports.list_for_user(
            user_id=actor.id, limit=limit, offset=offset
        )

    async def update(
        self,
        *,
        report_id: uuid.UUID,
        payload: ReportUpdate,
        actor: User,
    ) -> Report:
        # Load before authorizing so missing reports return 404 even when
        # the caller wouldn't have been allowed to edit them anyway.
        try:
            report = await self._reports.get(report_id, with_creator=True)
        except NotFoundError as exc:
            raise NotFound("report not found") from exc
        is_owner = report.user_id == actor.id
        if not actor.is_admin and not is_owner:
            raise PermissionDenied("not allowed to edit this report")

        # Snapshot the pre-edit state into report_versions.
        await self._reports.record_version(
            report_id=report.id,
            version=report.version,
            data=report.data,
            pdf_path=report.pdf_path,
            edited_by=actor.id,
        )

        new_case_id = payload.case_id or report.case_id
        new_payload = payload.payload or ReportPayload.model_validate(report.data)
        new_version = report.version + 1
        new_relpath = self._filestore.report_relpath(report.id, new_version)
        pdf_bytes = self._pdf.render_pdf(
            report_id=report.id,
            case_id=new_case_id,
            version=new_version,
            creator_email=report.creator.email if report.creator else "",
            payload=new_payload,
            created_at=report.created_at,
        )
        await self._filestore.write_bytes(new_relpath, pdf_bytes)

        report = await self._reports.replace_content(
            report,
            case_id=new_case_id,
            data=new_payload.model_dump(mode="json"),
            pdf_path=new_relpath,
        )

        await self._audit.record(
            actor_id=actor.id,
            action="report.update",
            resource_type="report",
            resource_id=str(report.id),
            details={
                "new_version": report.version,
                "via": "admin" if actor.is_admin and not is_owner else "owner",
            },
        )
        return report

    async def soft_delete(
        self, *, report_id: uuid.UUID, actor: User
    ) -> None:
        if not actor.is_admin:
            raise PermissionDenied("only admins may delete reports")
        try:
            report = await self._reports.get(report_id)
        except NotFoundError as exc:
            raise NotFound("report not found") from exc
        await self._reports.soft_delete(report)
        await self._audit.record(
            actor_id=actor.id,
            action="report.delete",
            resource_type="report",
            resource_id=str(report.id),
            details={},
        )

    async def stream_pdf(
        self, *, report_id: uuid.UUID, actor: User
    ) -> tuple[Report, AsyncIterator[bytes]]:
        report = await self.get_for_user(report_id, actor=actor)
        try:
            exists = await self._filestore.exists(report.pdf_path)
        except FileStoreError as exc:
            raise NotFound("report pdf unavailable") from exc
        if not exists:
            raise NotFound("report pdf missing on disk")
        await self._audit.record(
            actor_id=actor.id,
            action="report.download",
            resource_type="report",
            resource_id=str(report.id),
            details={"version": report.version},
        )
        return report, self._filestore.stream(report.pdf_path)

    def _authorize_read(self, report: Report, actor: User) -> None:
        if actor.is_admin:
            return
        if report.user_id != actor.id:
            raise PermissionDenied("not allowed to view this report")
