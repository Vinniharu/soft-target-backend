"""Server-side PDF rendering via Jinja2 + WeasyPrint.

The Jinja2 template in :mod:`app.templates.report` is the canonical
layout for the downloaded report. The frontend preview is UX-only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.report import ReportPayload

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


class PDFService:
    def __init__(self, template_dir: Path | None = None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir or _TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_html(
        self,
        *,
        report_id: uuid.UUID,
        case_id: str,
        version: int,
        creator_email: str,
        payload: ReportPayload,
        created_at: datetime,
    ) -> str:
        template = self._env.get_template("report.html.j2")
        context: dict[str, Any] = {
            "report_id": str(report_id),
            "case_id": case_id,
            "version": version,
            "creator_email": creator_email,
            "payload": payload.model_dump(mode="json"),
            "created_at": created_at.astimezone(UTC).isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        return template.render(**context)

    def render_pdf(
        self,
        *,
        report_id: uuid.UUID,
        case_id: str,
        version: int,
        creator_email: str,
        payload: ReportPayload,
        created_at: datetime,
    ) -> bytes:
        from weasyprint import HTML  # imported lazily — heavy C deps

        html = self.render_html(
            report_id=report_id,
            case_id=case_id,
            version=version,
            creator_email=creator_email,
            payload=payload,
            created_at=created_at,
        )
        return HTML(string=html).write_pdf()  # type: ignore[no-any-return]
