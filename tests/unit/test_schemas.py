"""Pydantic schema validation rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.report import (
    Coordinates,
    PrimaryTarget,
    ReportCreate,
    ReportPayload,
)
from app.schemas.user import UserCreate


def test_coordinates_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        Coordinates(latitude=91, longitude=0)
    with pytest.raises(ValidationError):
        Coordinates(latitude=0, longitude=181)


def test_user_create_requires_long_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.co", password="short")


def test_report_create_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ReportCreate.model_validate(
            {
                "case_id": "C1",
                "payload": {
                    "primary_target": {"name": "x"},
                    "ghost_field": True,
                },
            }
        )


def test_report_payload_allows_minimal_primary_target() -> None:
    payload = ReportPayload(
        primary_target=PrimaryTarget(), soft_targets=[], summary=None
    )
    assert payload.primary_target.imei_numbers == []
    assert payload.soft_targets == []
