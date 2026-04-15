"""SQLAlchemy ORM models.

Importing this package registers every model with the shared
:class:`~app.db.base.Base` metadata so Alembic ``--autogenerate`` sees
them.
"""

from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.report import Report
from app.models.report_version import ReportVersion
from app.models.user import User, UserRole

__all__ = [
    "AuditLog",
    "RefreshToken",
    "Report",
    "ReportVersion",
    "User",
    "UserRole",
]
