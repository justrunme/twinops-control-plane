"""Generic PLM adapters (file + REST; vendor stubs for later)."""

from twinops.plm.base import PlmAdapter
from twinops.plm.errors import (
    PlmAuthError,
    PlmConflictError,
    PlmError,
    PlmNotModified,
    PlmTransientError,
)
from twinops.plm.file import FilePlmAdapter
from twinops.plm.http_mock import MockPlmHTTPServer
from twinops.plm.mock import MockPlmAdapter, PlmItem
from twinops.plm.rest import CatalogFetch, RestPlmAdapter
from twinops.plm.stubs import TeamcenterStubAdapter, WindchillStubAdapter
from twinops.plm.sync import PlmSyncResult, PlmSyncSession, compute_backoff, revision_fingerprint

__all__ = [
    "CatalogFetch",
    "FilePlmAdapter",
    "MockPlmAdapter",
    "MockPlmHTTPServer",
    "PlmAdapter",
    "PlmAuthError",
    "PlmConflictError",
    "PlmError",
    "PlmItem",
    "PlmNotModified",
    "PlmSyncResult",
    "PlmSyncSession",
    "PlmTransientError",
    "RestPlmAdapter",
    "TeamcenterStubAdapter",
    "WindchillStubAdapter",
    "compute_backoff",
    "revision_fingerprint",
]
