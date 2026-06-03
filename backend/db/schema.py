"""Database schema — vacancies, publish history, full-text search."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

_VACANCIES = """
CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_user_id INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    telegram_text TEXT NOT NULL,
    whatsapp_text TEXT NOT NULL,
    channel_buttons_json TEXT NOT NULL DEFAULT '[]',
    png_path TEXT,
    poster_warning TEXT NOT NULL DEFAULT '',
    preview_message_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT,
    channel_message_id INTEGER
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_vacancies_manager_status
    ON vacancies (manager_user_id, status);
CREATE INDEX IF NOT EXISTS idx_vacancies_created
    ON vacancies (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vacancies_published
    ON vacancies (published_at DESC) WHERE published_at IS NOT NULL;
"""

_META = """
CREATE TABLE IF NOT EXISTS db_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS vacancies_fts USING fts5(
    source_text,
    telegram_text,
    content='vacancies',
    content_rowid='id',
    tokenize='unicode61'
);
"""

_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS vacancies_fts_ai AFTER INSERT ON vacancies BEGIN
    INSERT INTO vacancies_fts (rowid, source_text, telegram_text)
    VALUES (new.id, new.source_text, new.telegram_text);
END;
CREATE TRIGGER IF NOT EXISTS vacancies_fts_ad AFTER DELETE ON vacancies BEGIN
    INSERT INTO vacancies_fts (vacancies_fts, rowid, source_text, telegram_text)
    VALUES ('delete', old.id, old.source_text, old.telegram_text);
END;
CREATE TRIGGER IF NOT EXISTS vacancies_fts_au AFTER UPDATE ON vacancies BEGIN
    INSERT INTO vacancies_fts (vacancies_fts, rowid, source_text, telegram_text)
    VALUES ('delete', old.id, old.source_text, old.telegram_text);
    INSERT INTO vacancies_fts (rowid, source_text, telegram_text)
    VALUES (new.id, new.source_text, new.telegram_text);
END;
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_META)
    conn.executescript(_VACANCIES)
    conn.executescript(_INDEXES)
    conn.executescript(_FTS)
    conn.executescript(_FTS_TRIGGERS)
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
