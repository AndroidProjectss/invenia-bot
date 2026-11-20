"""SQLite-хранилище диалогов Invenia для Telegram, WhatsApp и админки."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.corpus import DATA


def database_path() -> Path:
    configured = os.environ.get("BOT_DB_PATH", "").strip()
    return Path(configured).expanduser() if configured else DATA / "invenia.sqlite3"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                external_id TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'ru',
                status TEXT NOT NULL DEFAULT 'open',
                bot_enabled INTEGER NOT NULL DEFAULT 1,
                current_topic INTEGER,
                unread_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(channel, external_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                external_message_id TEXT UNIQUE,
                direction TEXT NOT NULL,
                sender TEXT NOT NULL,
                text TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
            """
        )


def ensure_chat(
    channel: str,
    external_id: str,
    display_name: str = "",
    username: str = "",
    language: str = "ru",
) -> dict:
    init_db()
    timestamp = _now()
    with _connect() as db:
        db.execute(
            """
            INSERT INTO chats (
                channel, external_id, display_name, username, language,
                status, bot_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'open', 1, ?, ?)
            ON CONFLICT(channel, external_id) DO UPDATE SET
                display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE chats.display_name END,
                username = CASE WHEN excluded.username != '' THEN excluded.username ELSE chats.username END,
                language = excluded.language,
                updated_at = excluded.updated_at
            """,
            (channel, str(external_id), display_name, username, language, timestamp, timestamp),
        )
        row = db.execute(
            "SELECT * FROM chats WHERE channel = ? AND external_id = ?",
            (channel, str(external_id)),
        ).fetchone()
    return dict(row)


def add_message(
    chat_id: int,
    direction: str,
    sender: str,
    text: str,
    mode: str = "",
    external_message_id: str | None = None,
) -> dict | None:
    timestamp = _now()
    with _connect() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO messages (
                    chat_id, external_message_id, direction, sender, text, mode, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, external_message_id, direction, sender, text, mode, timestamp),
            )
        except sqlite3.IntegrityError:
            return None
        unread_delta = 1 if direction == "inbound" else 0
        db.execute(
            """
            UPDATE chats
            SET updated_at = ?, unread_count = unread_count + ?
            WHERE id = ?
            """,
            (timestamp, unread_delta, chat_id),
        )
        row = db.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_chat(chat_id: int, **fields) -> None:
    allowed = {"display_name", "language", "status", "bot_enabled", "current_topic", "unread_count"}
    selected = {key: value for key, value in fields.items() if key in allowed}
    if not selected:
        return
    selected["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in selected)
    with _connect() as db:
        db.execute(
            f"UPDATE chats SET {assignments} WHERE id = ?",  # nosec: keys are allow-listed
            (*selected.values(), chat_id),
        )


def get_chat(chat_id: int) -> dict | None:
    init_db()
    with _connect() as db:
        row = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def list_chats(status: str = "", channel: str = "", query: str = "") -> list[dict]:
    init_db()
    clauses = []
    params: list[str] = []
    if status:
        clauses.append("c.status = ?")
        params.append(status)
    if channel:
        clauses.append("c.channel = ?")
        params.append(channel)
    if query:
        clauses.append("(c.display_name LIKE ? OR c.username LIKE ? OR c.external_id LIKE ?)")
        pattern = f"%{query}%"
        params.extend([pattern, pattern, pattern])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as db:
        rows = db.execute(
            f"""
            SELECT c.*,
                   (SELECT text FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) AS last_message
            FROM chats c
            {where}
            ORDER BY c.updated_at DESC
            """,  # nosec: where contains fixed clauses only
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_messages(chat_id: int) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def dashboard_stats() -> dict:
    init_db()
    with _connect() as db:
        total = db.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        needs_human = db.execute("SELECT COUNT(*) FROM chats WHERE status = 'needs_human'").fetchone()[0]
        open_count = db.execute("SELECT COUNT(*) FROM chats WHERE status = 'open'").fetchone()[0]
        messages = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        telegram = db.execute("SELECT COUNT(*) FROM chats WHERE channel = 'telegram'").fetchone()[0]
        whatsapp = db.execute("SELECT COUNT(*) FROM chats WHERE channel = 'whatsapp'").fetchone()[0]
    return {
        "total": total,
        "needs_human": needs_human,
        "open": open_count,
        "messages": messages,
        "telegram": telegram,
        "whatsapp": whatsapp,
    }
