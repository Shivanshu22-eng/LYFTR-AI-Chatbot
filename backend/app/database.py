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

            CREATE TABLE IF NOT EXISTS image_analyses (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                analysis TEXT NOT NULL,
                model TEXT,
                latency_ms REAL,
                key_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS weather_queries (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                location TEXT NOT NULL,
                resolved_name TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                temperature_c REAL,
                humidity_pct REAL,
                rainfall_mm REAL,
                wind_speed_kmh REAL,
                condition TEXT,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS crop_recommendations (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                location TEXT,
                soil_type TEXT,
                soil_ph REAL,
                season TEXT,
                temperature_c REAL,
                rainfall_mm REAL,
                irrigation TEXT,
                recommendations_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
            );
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


def save_image_analysis(
    filename: str,
    mime_type: str,
    prompt: str,
    analysis: str,
    session_id: str | None = None,
    model: str | None = None,
    latency_ms: float | None = None,
    key_id: str | None = None,
) -> dict:
    """Persist an image analysis record."""
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO image_analyses
               (id, session_id, filename, mime_type, prompt, analysis, model, latency_ms, key_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, session_id, filename, mime_type, prompt, analysis, model, latency_ms, key_id, now),
        )
    return {
        "id": record_id,
        "session_id": session_id,
        "filename": filename,
        "mime_type": mime_type,
        "prompt": prompt,
        "analysis": analysis,
        "model": model,
        "latency_ms": latency_ms,
        "key_id": key_id,
        "created_at": now,
    }


def get_image_analyses(session_id: str | None = None, limit: int = 20) -> list[dict]:
    """Return recent image analyses, optionally filtered by session_id."""
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM image_analyses WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM image_analyses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def save_weather_query(
    location: str,
    resolved_name: str,
    latitude: float | None,
    longitude: float | None,
    temperature_c: float | None,
    humidity_pct: float | None,
    rainfall_mm: float | None,
    wind_speed_kmh: float | None,
    condition: str,
    source: str,
    fetched_at: str,
    session_id: str | None = None,
) -> dict:
    """Persist a weather query record."""
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO weather_queries
               (id, session_id, location, resolved_name, latitude, longitude, temperature_c,
                humidity_pct, rainfall_mm, wind_speed_kmh, condition, source, fetched_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id, session_id, location, resolved_name, latitude, longitude,
                temperature_c, humidity_pct, rainfall_mm, wind_speed_kmh, condition,
                source, fetched_at, now,
            ),
        )
    return {
        "id": record_id,
        "session_id": session_id,
        "location": location,
        "resolved_name": resolved_name,
        "latitude": latitude,
        "longitude": longitude,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "rainfall_mm": rainfall_mm,
        "wind_speed_kmh": wind_speed_kmh,
        "condition": condition,
        "source": source,
        "fetched_at": fetched_at,
        "created_at": now,
    }


def get_weather_queries(session_id: str | None = None, limit: int = 20) -> list[dict]:
    """Return recent weather queries, optionally filtered by session_id."""
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM weather_queries WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM weather_queries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def save_crop_recommendation(
    location: str | None,
    soil_type: str | None,
    soil_ph: float | None,
    season: str | None,
    temperature_c: float | None,
    rainfall_mm: float | None,
    irrigation: str | None,
    recommendations_json: str,
    assumptions_json: str,
    session_id: str | None = None,
) -> dict:
    """Persist a crop recommendation record."""
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO crop_recommendations
               (id, session_id, location, soil_type, soil_ph, season, temperature_c,
                rainfall_mm, irrigation, recommendations_json, assumptions_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id, session_id, location, soil_type, soil_ph, season,
                temperature_c, rainfall_mm, irrigation, recommendations_json,
                assumptions_json, now,
            ),
        )
    return {
        "id": record_id,
        "session_id": session_id,
        "location": location,
        "soil_type": soil_type,
        "soil_ph": soil_ph,
        "season": season,
        "temperature_c": temperature_c,
        "rainfall_mm": rainfall_mm,
        "irrigation": irrigation,
        "created_at": now,
    }


def get_crop_recommendations(session_id: str | None = None, limit: int = 20) -> list[dict]:
    """Return recent crop recommendations, optionally filtered by session_id."""
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM crop_recommendations WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM crop_recommendations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]
