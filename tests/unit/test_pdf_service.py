"""Jinja2 template rendering.

The WeasyPrint PDF path needs system libraries and is covered by
integration tests. Here we only assert the HTML context makes sense.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.services.pdf_service import PDFService
from tests.factories import make_report_payload


def test_render_html_contains_expected_fields() -> None:
    service = PDFService()
    html = service.render_html(
        report_id=uuid.uuid4(),
        case_id="CASE-TEST",
        version=3,
        creator_email="agent@example.com",
        payload=make_report_payload(soft_targets=2),
        created_at=datetime.now(UTC),
    )
    assert "CASE-TEST" in html
    assert "Primary Target" in html
    assert "Soft target #1" in html
    assert "Soft target #2" in html
    assert "CONFIDENTIAL" in html
    assert "agent@example.com" in html
