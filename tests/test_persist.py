"""SQLite persistence for control-plane state."""

from __future__ import annotations

from pathlib import Path

from twinops.api.persist import PersistentTwinStore, create_store


def test_persistent_store_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "twinops.sqlite"
    store = PersistentTwinStore(db)
    store.set_twin_meta({"name": "assembly-line-a", "reconciled": False})
    store.record(
        event_type="spike",
        timestamp="2026-07-31T10:43:00Z",
        summary="hot",
        payload={"hasDrift": True},
    )
    store.set_proposal({"status": {"applied": True}, "changes": []})
    store.set_drift({"status": {"hasDrift": True, "summary": {"CRITICAL": 1}}})
    assert store.audit_trail()
    store.close()

    restored = create_store(db_path=db)
    assert restored.twin_meta["name"] == "assembly-line-a"
    assert restored.latest_proposal and restored.latest_proposal["status"]["applied"]
    assert restored.timeline(limit=10)
    assert restored.latest_drift is not None
    assert restored.latest_drift["status"]["hasDrift"] is True
