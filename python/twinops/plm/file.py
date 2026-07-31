"""File-backed PLM adapter — JSON catalog on disk.

Same catalog shape as the mock demo (`items[]` with itemId/revision/lifecycle/prim).
Prefer this name when documenting the generic adapter SDK; MockPlmAdapter remains
the in-memory demo helper used by examples.
"""

from __future__ import annotations

from twinops.plm.mock import MockPlmAdapter


class FilePlmAdapter(MockPlmAdapter):
    """Vendor-neutral file adapter (JSON catalog)."""

    provider = "file"
