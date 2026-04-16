"""Test data factories.

Keep factories small and deterministic. They produce valid domain
objects with minimal fields — individual tests override as needed.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime

from app.models.user import User, UserRole
from app.schemas.report import (
    Coordinates,
    PrimaryTarget,
    ReportCreate,
    ReportPayload,
    SoftTarget,
)

_counter = itertools.count(1)


def make_user(
    *,
    email: str | None = None,
    name: str | None = None,
    role: UserRole = UserRole.user,
    password_hash: str = "$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
) -> User:
    n = next(_counter)
    user = User(
        id=uuid.uuid4(),
        email=email or f"user{n}@example.com",
        password_hash=password_hash,
        name=name or f"Test User {n}",
        role=role,
    )
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    return user


def make_report_payload(
    *,
    imei: list[str] | None = None,
    phones: list[str] | None = None,
    soft_targets: int = 1,
) -> ReportPayload:
    return ReportPayload(
        primary_target=PrimaryTarget(
            name="Subject A",
            imei_numbers=imei or ["490154203237518"],
            phone_numbers=phones or ["+15551234567"],
            location="42 Example Street",
            coordinates=Coordinates(latitude=51.5074, longitude=-0.1278),
            notes=None,
        ),
        soft_targets=[
            SoftTarget(
                phone=f"+1555000{i:04d}",
                location=f"Known associate #{i}",
                coordinates=Coordinates(
                    latitude=51.5 + i * 0.01, longitude=-0.1 + i * 0.01
                ),
                notes=None,
            )
            for i in range(1, soft_targets + 1)
        ],
        summary="Preliminary surveillance summary.",
    )


def make_report_create(case_id: str = "CASE-0001") -> ReportCreate:
    return ReportCreate(case_id=case_id, payload=make_report_payload())
