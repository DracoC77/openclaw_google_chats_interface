"""SQLite database for message history, state, and auth tokens."""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender_name TEXT NOT NULL,
    sender_email TEXT DEFAULT '',
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """Thin wrapper around SQLite with methods for messages, state, and auth."""

    def __init__(self, db_path: str | None = None):
        path = db_path or config.DB_PATH
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        log.info("Database initialised at %s", path)

    # -- messages --

    def upsert_messages(self, messages: list[dict[str, Any]]) -> int:
        """Insert messages, skipping duplicates. Returns count of new rows."""
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for msg in messages:
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO messages
                       (id, sender_name, sender_email, text, created_at, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        msg["id"],
                        msg["sender_name"],
                        msg.get("sender_email", ""),
                        msg["text"],
                        msg["created_at"],
                        now,
                    ),
                )
                inserted += self.conn.total_changes  # rough; good enough
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return inserted

    def get_messages(
        self,
        *,
        since: str | None = None,
        limit: int = 100,
        sender: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch messages, optionally filtered by time and sender."""
        clauses: list[str] = []
        params: list[Any] = []

        if since:
            clauses.append("created_at > ?")
            params.append(since)
        if sender:
            clauses.append("sender_name LIKE ?")
            params.append(f"%{sender}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM messages {where} ORDER BY created_at ASC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unread_messages(self) -> list[dict[str, Any]]:
        """Messages since the last read marker."""
        marker = self.get_state("read_marker")
        if marker:
            return self.get_messages(since=marker, limit=500)
        # No marker set — return the last 50 messages
        return self.get_messages(limit=50)

    def mark_read(self, timestamp: str | None = None) -> str:
        """Advance the read marker. Defaults to now."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        self.set_state("read_marker", ts)
        return ts

    def message_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM messages").fetchone()
        return row["cnt"]

    def latest_message_time(self) -> str | None:
        row = self.conn.execute(
            "SELECT created_at FROM messages ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return row["created_at"] if row else None

    def unread_count(self) -> int:
        marker = self.get_state("read_marker")
        if marker:
            row = self.conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE created_at > ?",
                (marker,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages"
            ).fetchone()
        return row["cnt"]

    # -- key-value state --

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    # -- auth tokens --

    def get_auth(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM auth WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_auth(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO auth (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()
