"""
LYFTR AI Chatbot - SQLite Database Module
Handles database initialization, session management, and message storage.
"""

import sqlite3
import os
import uuid
from datetime import datetime
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "lyftr.db"))


def get_db_path() -> str:
    """Return the absolute path to the SQLite database file."""
    return os.path.abspath(DATABASE_PATH)


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables."""
    db_dir = os.path.dirname(get_db_path())
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                model TEXT,
                resolution_source TEXT,
                latency_ms REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                key_id TEXT,
                fallback_attempts INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
        """)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "source" in cols and "resolution_source" not in cols:
            conn.execute("ALTER TABLE messages RENAME COLUMN source TO resolution_source")


def create_session(title: str = "New Chat") -> dict:
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}


def get_sessions() -> list[dict]:
    """Return all sessions ordered by most recently updated."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    """Return a single session by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def update_session_title(session_id: str, title: str):
    """Update the title of a session."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )


def save_message(
    session_id: str,
    role: str,
    content: str,
    model: str | None = None,
    resolution_source: str | None = None,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    key_id: str | None = None,
    fallback_attempts: int | None = None,
) -> dict:
    """Save a message to the database."""
    message_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO messages
               (id, session_id, role, content, model, resolution_source, latency_ms,
                input_tokens, output_tokens, key_id, fallback_attempts, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, role, content, model, resolution_source, latency_ms,
             input_tokens, output_tokens, key_id, fallback_attempts, now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
    return {
        "id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "model": model,
        "resolution_source": resolution_source,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "key_id": key_id,
        "fallback_attempts": fallback_attempts,
        "created_at": now,
    }


def get_messages(session_id: str) -> list[dict]:
    """Return all messages for a session in chronological order."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]
