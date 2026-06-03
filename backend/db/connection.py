"""SQLite connection tuned for many rows and concurrent reads."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_DB = ROOT / "data" / "manager.db"

_conn: Optional[sqlite3.Connection] = None
_lock = Lock()


def db_path() -> Path:
    raw = (os.environ.get("MANAGER_DB_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_DB


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # 256 MB mmap for large DBs
    conn.execute("PRAGMA cache_size=-64000")  # ~64 MB page cache
    conn.execute("PRAGMA foreign_keys=ON")


def get_connection() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        _conn = conn
        return conn


def close_connection() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def init_db() -> None:
    from db.schema import apply_schema

    conn = get_connection()
    apply_schema(conn)
    conn.commit()
