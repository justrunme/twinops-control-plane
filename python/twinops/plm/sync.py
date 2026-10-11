"""PLM poll/sync session: ETag polling, backoff, conflict, idempotent resync."""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twinops.plm.errors import (
    PlmAuthError,
    PlmConflictError,
    PlmNotModified,
    PlmTransientError,
)
from twinops.plm.rest import RestPlmAdapter


@dataclass
class PlmSyncResult:
    changed: bool
    etag: str | None
    fingerprint: str | None
    items: int = 0
    resynced: bool = False
    conflict: bool = False
    conflict_message: str | None = None
    error: str | None = None
    not_modified: bool = False
    report: dict[str, Any] = field(default_factory=dict)

    def to_status(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "etag": self.etag,
            "fingerprint": self.fingerprint,
            "items": self.items,
            "resynced": self.resynced,
            "conflict": self.conflict,
            "conflictMessage": self.conflict_message,
            "error": self.error,
            "notModified": self.not_modified,
        }


def revision_fingerprint(items: list[Any]) -> str:
    pairs = sorted(
        (
            getattr(item, "item_id", None) or item.get("itemId"),
            getattr(item, "revision", None) or item.get("revision"),
        )
        for item in items
    )
    raw = json.dumps(pairs, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_backoff(
    attempt: int, *, base: float = 0.1, cap: float = 5.0, jitter: bool = True
) -> float:
    """Exponential backoff with full jitter (AWS-style)."""
    exp = min(cap, base * (2**attempt))
    if not jitter:
        return exp
    return random.uniform(0, exp)


class PlmSyncSession:
    """Stateful poller around RestPlmAdapter.

    After an outage (transient/auth cleared), the next successful poll increments
    ``resync_count`` exactly once — even when the catalog returns 304.
    """

    def __init__(
        self,
        adapter: RestPlmAdapter,
        *,
        manifest_path: str | Path | None = None,
        write_manifest: bool = True,
    ) -> None:
        self.adapter = adapter
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.write_manifest = write_manifest
        self._lock = threading.RLock()
        self.etag: str | None = None
        self.fingerprint: str | None = None
        self.resync_count = 0
        self.consecutive_failures = 0
        self.in_outage = False
        self.conflict = False
        self.conflict_message: str | None = None
        self.last_error: str | None = None
        self.last_sync_at: float | None = None
        self.polls = 0
        self.changes = 0

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "etag": self.etag,
                "fingerprint": self.fingerprint,
                "resyncCount": self.resync_count,
                "consecutiveFailures": self.consecutive_failures,
                "inOutage": self.in_outage,
                "conflict": self.conflict,
                "conflictMessage": self.conflict_message,
                "lastError": self.last_error,
                "lastSyncAt": self.last_sync_at,
                "polls": self.polls,
                "changes": self.changes,
            }

    def poll(self) -> PlmSyncResult:
        with self._lock:
            self.polls += 1
            was_outage = self.in_outage
            try:
                fetched = self.adapter.fetch_catalog(if_none_match=self.etag)
            except PlmNotModified as exc:
                resynced = False
                if was_outage:
                    self.resync_count += 1
                    self.in_outage = False
                    resynced = True
                self.consecutive_failures = 0
                self.last_error = None
                self.last_sync_at = time.time()
                if exc.etag:
                    self.etag = exc.etag
                return PlmSyncResult(
                    changed=False,
                    etag=self.etag,
                    fingerprint=self.fingerprint,
                    not_modified=True,
                    resynced=resynced,
                )
            except PlmConflictError as exc:
                self.conflict = True
                self.conflict_message = str(exc)
                self.last_error = str(exc)
                self.consecutive_failures += 1
                self.in_outage = True
                return PlmSyncResult(
                    changed=False,
                    etag=self.etag,
                    fingerprint=self.fingerprint,
                    conflict=True,
                    conflict_message=str(exc),
                    error=str(exc),
                )
            except (PlmTransientError, PlmAuthError) as exc:
                self.consecutive_failures += 1
                self.in_outage = True
                self.last_error = str(exc)
                return PlmSyncResult(
                    changed=False,
                    etag=self.etag,
                    fingerprint=self.fingerprint,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                self.consecutive_failures += 1
                self.in_outage = True
                self.last_error = str(exc)
                return PlmSyncResult(
                    changed=False,
                    etag=self.etag,
                    fingerprint=self.fingerprint,
                    error=str(exc),
                )

            items = fetched.items
            fp = revision_fingerprint(items)
            changed = fp != self.fingerprint
            resynced = False
            if was_outage:
                self.resync_count += 1
                self.in_outage = False
                resynced = True

            self.etag = fetched.etag
            self.fingerprint = fp
            self.consecutive_failures = 0
            self.last_error = None
            self.conflict = False
            self.conflict_message = None
            self.last_sync_at = time.time()

            report: dict[str, Any] = {}
            if changed and self.manifest_path is not None:
                report = self.adapter.sync_manifest(
                    self.manifest_path, write=self.write_manifest
                )
                self.changes += 1
            elif changed:
                self.changes += 1

            return PlmSyncResult(
                changed=changed,
                etag=self.etag,
                fingerprint=self.fingerprint,
                items=len(items),
                resynced=resynced,
                report=report,
            )

    def poll_with_retry(
        self,
        *,
        max_attempts: int = 5,
        base: float = 0.05,
        cap: float = 1.0,
    ) -> PlmSyncResult:
        last = self.poll()
        attempt = 0
        while last.error and not last.conflict and attempt < max_attempts - 1:
            delay = compute_backoff(attempt, base=base, cap=cap)
            time.sleep(delay)
            attempt += 1
            last = self.poll()
        return last
