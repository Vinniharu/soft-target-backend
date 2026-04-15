"""Typed repository-layer errors.

Repositories raise these (never HTTP exceptions). Services either handle
them or translate them into service-layer errors, and the global
exception handler maps service errors to HTTP responses.
"""

from __future__ import annotations


class RepositoryError(Exception):
    """Base class for repository errors."""


class NotFoundError(RepositoryError):
    """Raised when a looked-up row does not exist."""


class ConflictError(RepositoryError):
    """Raised on unique-constraint violations or similar conflicts."""
