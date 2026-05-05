"""Report business logic and authorization.

The service owns every "can this caller do X to this report?" decision.
Endpoints never touch repositories directly.

Visibility model (3-tier):

    admin       — sees and acts on every report
    org_owner   — sees and acts on every report where
                  ``report.organisation_id == actor.organisation_id``
    user        — sees and acts on every report where
                  ``report.user_id == actor.id``

Reports are stamped with the creator's ``organisation_id`` at write
time and stay attributed to that org for life.
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
            organisation_id=creator.organisation_id,
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
            details={
                "case_id": report.case_id,
                "organisation_id": (
                    str(creator.organisation_id)
                    if creator.organisation_id
                    else None
                ),
            },
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

    async def list_visible(
        self, *, actor: User, limit: int, offset: int
    ) -> tuple[list[Report], int]:
        """Three-way branch:
        - admin: every report
        - org_owner: every report in own org
        - user: own reports only
        """

        if actor.is_admin:
            return await self._reports.list_all(limit=limit, offset=offset)
        if actor.is_org_owner and actor.organisation_id is not None:
            return await self._reports.list_for_org(
                organisation_id=actor.organisation_id,
                limit=limit,
                offset=offset,
            )
        return await self._reports.list_for_user(
            user_id=actor.id, limit=limit, offset=offset
        )

    async def list_for_org(
        self,
        *,
        organisation_id: uuid.UUID,
        actor: User,
        limit: int,
        offset: int,
    ) -> tuple[list[Report], int]:
        """Cross-cutting list used by both /admin/organisations/{id}/reports
        (admin) and /org/reports (org_owner). The service confirms the
        actor is allowed to see the requested org."""

        if actor.is_admin:
            return await self._reports.list_for_org(
                organisation_id=organisation_id, limit=limit, offset=offset
            )
        if (
            actor.is_org_owner
            and actor.organisation_id == organisation_id
        ):
            return await self._reports.list_for_org(
                organisation_id=organisation_id, limit=limit, offset=offset
            )
        raise PermissionDenied(
            "not allowed to list reports in this organisation"
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
        via = self._authorize_write(report, actor)

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
            details={"new_version": report.version, "via": via},
        )
        return report

    async def soft_delete(
        self, *, report_id: uuid.UUID, actor: User
    ) -> None:
        try:
            report = await self._reports.get(report_id)
        except NotFoundError as exc:
            raise NotFound("report not found") from exc
        via = self._authorize_delete(report, actor)
        await self._reports.soft_delete(report)
        await self._audit.record(
            actor_id=actor.id,
            action="report.delete",
            resource_type="report",
            resource_id=str(report.id),
            details={"via": via},
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

    # ------------------------------------------------------------------
    # Authorization helpers
    # ------------------------------------------------------------------

    def _authorize_read(self, report: Report, actor: User) -> None:
        if actor.is_admin:
            return
        if (
            actor.is_org_owner
            and actor.organisation_id is not None
            and report.organisation_id == actor.organisation_id
        ):
            return
        if report.user_id == actor.id:
            return
        raise PermissionDenied("not allowed to view this report")

    def _authorize_write(self, report: Report, actor: User) -> str:
        """Returns the audit ``via`` tag describing how authz was satisfied."""

        if actor.is_admin:
            return "admin"
        if (
            actor.is_org_owner
            and actor.organisation_id is not None
            and report.organisation_id == actor.organisation_id
        ):
            return "org_owner"
        if report.user_id == actor.id:
            return "owner"
        raise PermissionDenied("not allowed to edit this report")

    def _authorize_delete(self, report: Report, actor: User) -> str:
        if actor.is_admin:
            return "admin"
        if (
            actor.is_org_owner
            and actor.organisation_id is not None
            and report.organisation_id == actor.organisation_id
        ):
            return "org_owner"
        # Plain users cannot delete (per spec).
        raise PermissionDenied("not allowed to delete this report")
