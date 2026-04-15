"""Typed service-layer errors.

These are mapped to HTTP responses by the global exception handler in
:mod:`app.api.errors`. Services never raise HTTP exceptions directly.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for service errors."""


class NotFound(ServiceError):
    pass


class PermissionDenied(ServiceError):
    pass


class InvalidCredentials(ServiceError):
    pass


class Conflict(ServiceError):
    pass


class RateLimited(ServiceError):
    pass
