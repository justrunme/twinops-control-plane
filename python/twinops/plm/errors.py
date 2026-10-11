"""Typed errors for REST PLM reliability."""

from __future__ import annotations


class PlmError(RuntimeError):
    """Base PLM adapter error."""


class PlmAuthError(PlmError):
    """Authentication / authorization failure (401/403)."""


class PlmConflictError(PlmError):
    """Version conflict (HTTP 409)."""

    def __init__(
        self, message: str, *, item_id: str | None = None, etag: str | None = None
    ) -> None:
        super().__init__(message)
        self.item_id = item_id
        self.etag = etag


class PlmTransientError(PlmError):
    """Retryable failure (5xx, timeout, connection reset)."""


class PlmNotModified(PlmError):
    """Catalog unchanged (HTTP 304). Not a failure — used as a control signal."""

    def __init__(self, etag: str = "") -> None:
        super().__init__(etag or "not modified")
        self.etag = etag
