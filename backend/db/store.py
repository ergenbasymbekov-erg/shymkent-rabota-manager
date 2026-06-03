"""Vacancy persistence — pending posts, publish history, search."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.connection import get_connection
from schema import TelegramButton


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class StoredPending:
    vacancy_id: int
    source_text: str
    telegram_preview_text: str
    telegram_channel_text: str
    whatsapp_text: str
    channel_buttons: list[TelegramButton]
    png_path: Optional[Path]
    poster_warning: str
    preview_message_ids: list[int]


def _buttons_to_json(buttons: list[TelegramButton]) -> str:
    return json.dumps([b.model_dump() for b in buttons], ensure_ascii=False)


def _buttons_from_json(raw: str) -> list[TelegramButton]:
    if not raw:
        return []
    data = json.loads(raw)
    return [TelegramButton.model_validate(item) for item in data]


def _ids_to_json(ids: list[int]) -> str:
    return json.dumps(ids)


def _ids_from_json(raw: str) -> list[int]:
    if not raw:
        return []
    return [int(x) for x in json.loads(raw)]


class VacancyStore:
    """Thread-safe SQLite access (call from asyncio.to_thread in the bot)."""

    def save_pending(
        self,
        manager_user_id: int,
        *,
        source_text: str,
        telegram_preview_text: str,
        telegram_channel_text: str,
        whatsapp_text: str,
        channel_buttons: list[TelegramButton],
        png_path: Optional[Path],
        poster_warning: str = "",
        preview_message_ids: Optional[list[int]] = None,
    ) -> int:
        conn = get_connection()
        now = _utc_now()
        conn.execute(
            "UPDATE vacancies SET status = 'cancelled', updated_at = ? "
            "WHERE manager_user_id = ? AND status = 'pending'",
            (now, manager_user_id),
        )
        cur = conn.execute(
            """
            INSERT INTO vacancies (
                manager_user_id, source_text, telegram_text, whatsapp_text,
                channel_buttons_json, png_path, poster_warning,
                preview_message_ids_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                manager_user_id,
                source_text,
                telegram_preview_text,
                whatsapp_text,
                _buttons_to_json(channel_buttons),
                str(png_path) if png_path else None,
                poster_warning or "",
                _ids_to_json(preview_message_ids or []),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)

    def update_preview_ids(self, vacancy_id: int, message_ids: list[int]) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE vacancies SET preview_message_ids_json = ?, updated_at = ? WHERE id = ?",
            (_ids_to_json(message_ids), _utc_now(), vacancy_id),
        )
        conn.commit()

    def get_pending(self, manager_user_id: int) -> Optional[StoredPending]:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT * FROM vacancies
            WHERE manager_user_id = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
            """,
            (manager_user_id,),
        ).fetchone()
        if not row:
            return None
        png = row["png_path"]
        return StoredPending(
            vacancy_id=int(row["id"]),
            source_text=row["source_text"],
            telegram_preview_text=row["telegram_text"],
            telegram_channel_text=row["telegram_text"],
            whatsapp_text=row["whatsapp_text"],
            channel_buttons=_buttons_from_json(row["channel_buttons_json"]),
            png_path=Path(png) if png else None,
            poster_warning=row["poster_warning"] or "",
            preview_message_ids=_ids_from_json(row["preview_message_ids_json"]),
        )

    def clear_pending(self, manager_user_id: int, *, status: str = "cancelled") -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE vacancies SET status = ?, updated_at = ? "
            "WHERE manager_user_id = ? AND status = 'pending'",
            (status, _utc_now(), manager_user_id),
        )
        conn.commit()

    def mark_published(
        self,
        vacancy_id: int,
        *,
        channel_message_id: Optional[int] = None,
    ) -> None:
        now = _utc_now()
        conn = get_connection()
        conn.execute(
            """
            UPDATE vacancies SET
                status = 'published',
                updated_at = ?,
                published_at = ?,
                channel_message_id = ?
            WHERE id = ?
            """,
            (now, now, channel_message_id, vacancy_id),
        )
        conn.commit()

    def count_published(self, manager_user_id: int) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM vacancies WHERE manager_user_id = ? AND status = 'published'",
            (manager_user_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Full-text search over source and formatted text."""
        q = query.strip()
        if not q:
            return []
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT v.id, v.source_text, v.status, v.published_at, v.created_at
            FROM vacancies_fts fts
            JOIN vacancies v ON v.id = fts.rowid
            WHERE vacancies_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_published(self, manager_user_id: int, *, limit: int = 10) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT id, source_text, published_at
            FROM vacancies
            WHERE manager_user_id = ? AND status = 'published'
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (manager_user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
