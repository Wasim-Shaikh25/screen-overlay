"""Local SQLite storage for conversation history.

All data stays on the user's machine. Nothing is uploaded except the explicit
requests the user sends to OpenAI through :mod:`overlay.ai_client`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Message:
    """A single stored conversation turn."""

    role: str
    content: str
    created_at: str


class ConversationStore:
    """Thin SQLite-backed append/read store for conversation turns."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def add(self, role: str, content: str) -> None:
        """Persist a single turn (``role`` is 'user', 'assistant', or 'system')."""
        self._conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def recent(self, limit: int = 50) -> list[Message]:
        """Return the most recent messages in chronological order."""
        rows = self._conn.execute(
            "SELECT role, content, created_at FROM messages "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        messages = [
            Message(role=r["role"], content=r["content"], created_at=r["created_at"])
            for r in rows
        ]
        messages.reverse()
        return messages

    def clear(self) -> None:
        """Delete all stored messages."""
        self._conn.execute("DELETE FROM messages")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
