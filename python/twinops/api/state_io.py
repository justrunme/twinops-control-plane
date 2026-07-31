"""Backup / restore helpers for TwinOps SQLite state."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


def backup_sqlite(db_path: str | Path, out_path: str | Path) -> Path:
    """Copy a SQLite database using the online backup API when possible."""
    src = Path(db_path)
    dst = Path(out_path)
    if not src.is_file():
        raise FileNotFoundError(f"database not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(src)) as src_conn:
        with sqlite3.connect(str(dst)) as dst_conn:
            src_conn.backup(dst_conn)
    return dst.resolve()


def restore_sqlite(db_path: str | Path, from_path: str | Path) -> Path:
    """Replace db_path with a backup file (caller must stop writers first)."""
    src = Path(from_path)
    dst = Path(db_path)
    if not src.is_file():
        raise FileNotFoundError(f"backup not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Validate backup opens as SQLite.
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as conn:
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    shutil.copy2(src, dst)
    return dst.resolve()
