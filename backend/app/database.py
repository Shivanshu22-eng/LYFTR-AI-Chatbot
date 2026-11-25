"""
LYFTR AI Chatbot - SQLite Database Module
Handles database initialization, session management, message storage,
user auth, image generation history, admin audit logs, and permissions.
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
    """Initialize the database with required tables (safe, idempotent)."""
    db_dir = os.path.dirname(get_db_path())
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
            -- ---- Original tables ----

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

            -- ---- Auth & user management ----

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
                    CHECK(role IN ('user', 'authorized_creator', 'admin')),
                is_active INTEGER NOT NULL DEFAULT 1,
                daily_gen_limit INTEGER NOT NULL DEFAULT 10,
                allowed_categories TEXT NOT NULL DEFAULT '["safe"]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

            -- ---- Image generation ----

            CREATE TABLE IF NOT EXISTS image_generations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                style TEXT NOT NULL DEFAULT 'photorealistic',
                aspect_ratio TEXT NOT NULL DEFAULT '1:1',
                num_images INTEGER NOT NULL DEFAULT 1,
                images_json TEXT NOT NULL DEFAULT '[]',
                provider TEXT NOT NULL DEFAULT 'pollinations.ai',
                model TEXT NOT NULL DEFAULT 'flux',
                latency_ms REAL,
                status TEXT NOT NULL DEFAULT 'success'
                    CHECK(status IN ('success', 'failed', 'blocked')),
                error_message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_image_gen_user_id ON image_generations(user_id);
            CREATE INDEX IF NOT EXISTS idx_image_gen_created_at ON image_generations(created_at);

            -- ---- Global settings ----

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );

            -- ---- Admin audit log ----

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_user_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_logs_admin_id ON audit_logs(admin_id);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
        """)

        # Migrate old `source` column to `resolution_source` if needed
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "source" in cols and "resolution_source" not in cols:
            conn.execute("ALTER TABLE messages RENAME COLUMN source TO resolution_source")

        # Seed default settings if not present
        now = datetime.utcnow().isoformat()
        defaults = {
            "image_generation_enabled": "true",
            "image_generation_allowed_categories": '["safe"]',
            "image_generation_default_daily_limit": "10",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )


# ===========================================================================
# Original CRUD — sessions, messages, image_analyses, weather, crop
# (Unchanged — preserved for backward compatibility)
# ===========================================================================

def create_session(title: str = "New Chat") -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}


def get_sessions() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def update_session_title(session_id: str, title: str):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )


def save_message(
    session_id: str, role: str, content: str,
    model: str | None = None, resolution_source: str | None = None,
    latency_ms: float | None = None, input_tokens: int | None = None,
    output_tokens: int | None = None, key_id: str | None = None,
    fallback_attempts: int | None = None,
) -> dict:
    message_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO messages
               (id, session_id, role, content, model, resolution_source, latency_ms,
                input_tokens, output_tokens, key_id, fallback_attempts, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, role, content, model, resolution_source,
             latency_ms, input_tokens, output_tokens, key_id, fallback_attempts, now),
        )
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    return {
        "id": message_id, "session_id": session_id, "role": role,
        "content": content, "model": model, "resolution_source": resolution_source,
        "latency_ms": latency_ms, "input_tokens": input_tokens,
        "output_tokens": output_tokens, "key_id": key_id,
        "fallback_attempts": fallback_attempts, "created_at": now,
    }


def get_messages(session_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_image_analysis(
    filename: str, mime_type: str, prompt: str, analysis: str,
    session_id: str | None = None, model: str | None = None,
    latency_ms: float | None = None, key_id: str | None = None,
) -> dict:
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
        "id": record_id, "session_id": session_id, "filename": filename,
        "mime_type": mime_type, "prompt": prompt, "analysis": analysis,
        "model": model, "latency_ms": latency_ms, "key_id": key_id, "created_at": now,
    }


def get_image_analyses(session_id: str | None = None, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM image_analyses WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM image_analyses ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def save_weather_query(
    location: str, resolved_name: str, latitude: float | None, longitude: float | None,
    temperature_c: float | None, humidity_pct: float | None, rainfall_mm: float | None,
    wind_speed_kmh: float | None, condition: str, source: str, fetched_at: str,
    session_id: str | None = None,
) -> dict:
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO weather_queries
               (id, session_id, location, resolved_name, latitude, longitude, temperature_c,
                humidity_pct, rainfall_mm, wind_speed_kmh, condition, source, fetched_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, session_id, location, resolved_name, latitude, longitude,
             temperature_c, humidity_pct, rainfall_mm, wind_speed_kmh, condition,
             source, fetched_at, now),
        )
    return {
        "id": record_id, "session_id": session_id, "location": location,
        "resolved_name": resolved_name, "latitude": latitude, "longitude": longitude,
        "temperature_c": temperature_c, "humidity_pct": humidity_pct,
        "rainfall_mm": rainfall_mm, "wind_speed_kmh": wind_speed_kmh,
        "condition": condition, "source": source, "fetched_at": fetched_at, "created_at": now,
    }


def get_weather_queries(session_id: str | None = None, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM weather_queries WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM weather_queries ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def save_crop_recommendation(
    location: str | None, soil_type: str | None, soil_ph: float | None,
    season: str | None, temperature_c: float | None, rainfall_mm: float | None,
    irrigation: str | None, recommendations_json: str, assumptions_json: str,
    session_id: str | None = None,
) -> dict:
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO crop_recommendations
               (id, session_id, location, soil_type, soil_ph, season, temperature_c,
                rainfall_mm, irrigation, recommendations_json, assumptions_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, session_id, location, soil_type, soil_ph, season,
             temperature_c, rainfall_mm, irrigation, recommendations_json,
             assumptions_json, now),
        )
    return {
        "id": record_id, "session_id": session_id, "location": location,
        "soil_type": soil_type, "soil_ph": soil_ph, "season": season,
        "temperature_c": temperature_c, "rainfall_mm": rainfall_mm,
        "irrigation": irrigation, "created_at": now,
    }


def get_crop_recommendations(session_id: str | None = None, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM crop_recommendations WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM crop_recommendations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# ===========================================================================
# User management
# ===========================================================================

def create_user(email: str, password_hash: str, role: str = "user") -> dict:
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO users (id, email, password_hash, role, is_active,
               daily_gen_limit, allowed_categories, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, 10, '["safe"]', ?, ?)""",
            (user_id, email.lower().strip(), password_hash, role, now, now),
        )
    return {"id": user_id, "email": email, "role": role, "is_active": True, "created_at": now}


def get_user_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_all_users(limit: int = 100, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, email, role, is_active, daily_gen_limit, allowed_categories, created_at, updated_at "
            "FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def update_user_permissions(
    user_id: str,
    role: str | None = None,
    is_active: bool | None = None,
    daily_gen_limit: int | None = None,
    allowed_categories: list | None = None,
) -> dict | None:
    import json as _json
    now = datetime.utcnow().isoformat()
    updates = []
    params = []
    if role is not None:
        updates.append("role = ?")
        params.append(role)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if daily_gen_limit is not None:
        updates.append("daily_gen_limit = ?")
        params.append(daily_gen_limit)
    if allowed_categories is not None:
        updates.append("allowed_categories = ?")
        params.append(_json.dumps(allowed_categories))
    if not updates:
        return get_user_by_id(user_id)
    updates.append("updated_at = ?")
    params.append(now)
    params.append(user_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
        )
    return get_user_by_id(user_id)


def count_user_generations_today(user_id: str) -> int:
    today = datetime.utcnow().date().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM image_generations "
            "WHERE user_id = ? AND status = 'success' AND created_at >= ?",
            (user_id, today),
        ).fetchone()
    return row["cnt"] if row else 0


# ===========================================================================
# Image generation records
# ===========================================================================

def save_image_generation(
    user_id: str, prompt: str, style: str, aspect_ratio: str,
    num_images: int, images_json: str, provider: str, model: str,
    latency_ms: float | None, status: str, error_message: str | None = None,
) -> dict:
    record_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO image_generations
               (id, user_id, prompt, style, aspect_ratio, num_images, images_json,
                provider, model, latency_ms, status, error_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, user_id, prompt, style, aspect_ratio, num_images, images_json,
             provider, model, latency_ms, status, error_message, now),
        )
    return {
        "id": record_id, "user_id": user_id, "prompt": prompt, "style": style,
        "aspect_ratio": aspect_ratio, "num_images": num_images,
        "provider": provider, "model": model, "latency_ms": latency_ms,
        "status": status, "error_message": error_message, "created_at": now,
    }


def get_user_image_generations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM image_generations WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_image_generations(limit: int = 100, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ig.*, u.email as user_email FROM image_generations ig "
            "LEFT JOIN users u ON ig.user_id = u.id "
            "ORDER BY ig.created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_image_generation(generation_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM image_generations WHERE id = ?", (generation_id,)
        ).fetchone()
    return dict(row) if row else None


# ===========================================================================
# App settings
# ===========================================================================

def get_setting(key: str, default: str | None = None) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str, updated_by: str | None = None):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)",
            (key, value, now, updated_by),
        )


def get_all_settings() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ===========================================================================
# Audit log
# ===========================================================================

def save_audit_log(
    admin_id: str, action: str,
    target_user_id: str | None = None, details: str | None = None,
) -> dict:
    log_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_logs (id, admin_id, action, target_user_id, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (log_id, admin_id, action, target_user_id, details, now),
        )
    return {
        "id": log_id, "admin_id": admin_id, "action": action,
        "target_user_id": target_user_id, "details": details, "created_at": now,
    }


def get_audit_logs(limit: int = 100, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT al.*, u.email as admin_email
               FROM audit_logs al
               LEFT JOIN users u ON al.admin_id = u.id
               ORDER BY al.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]
