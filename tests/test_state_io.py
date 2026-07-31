"""SQLite backup / restore helpers."""

from __future__ import annotations

from pathlib import Path

from twinops.api.persist import PersistentTwinStore
from twinops.api.state_io import backup_sqlite, restore_sqlite


def test_backup_and_restore_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "twinops.sqlite"
    store = PersistentTwinStore(db)
    store.set_twin_meta({"name": "assembly-line-a"})
    store.record(
        event_type="telemetry",
        timestamp="2026-07-31T12:00:00Z",
        summary="ok",
        payload={},
    )
    store.close()

    backup = tmp_path / "backup.sqlite"
    backup_sqlite(db, backup)
    assert backup.is_file()

    restored_path = tmp_path / "restored.sqlite"
    restore_sqlite(restored_path, backup)
    restored = PersistentTwinStore(restored_path)
    assert restored.twin_meta["name"] == "assembly-line-a"
    assert restored.timeline(limit=5)
    restored.close()
