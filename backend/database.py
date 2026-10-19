"""
Scriber — High-Performance SQLite Database for Transcription History
Features WAL mode for concurrent non-blocking reads/writes, index optimization,
strict POSIX privacy permissions, and SQL-level aggregation.
"""

import os
import sqlite3
from pathlib import Path

try:
    from backend.config import DB_FILE
except ImportError:
    from config import DB_FILE


def _resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return DB_FILE


def _connect(db_path: Path | str | None = None):
    """Connect to SQLite database with WAL mode and resilient busy timeout."""
    target_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(target_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db(db_path: Path | str | None = None):
    """Create the transcriptions table, indices, and ensure privacy permissions."""
    target_path = _resolve_db_path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target_path.parent, 0o700)
    except Exception:
        pass

    conn = _connect(target_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_text TEXT NOT NULL,
                cleaned_text TEXT NOT NULL,
                duration_seconds REAL,
                whisper_model TEXT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_id_desc ON transcriptions(id DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_timestamp ON transcriptions(timestamp);")
    conn.close()

    if target_path.exists():
        try:
            os.chmod(target_path, 0o600)
        except Exception:
            pass


def save_transcription(
    raw_text: str,
    cleaned_text: str,
    duration: float,
    model: str,
    db_path: Path | str | None = None,
) -> int:
    """Save a transcription and return its ID."""
    conn = _connect(db_path)
    with conn:
        cursor = conn.execute(
            "INSERT INTO transcriptions (raw_text, cleaned_text, duration_seconds, whisper_model) VALUES (?, ?, ?, ?)",
            (raw_text, cleaned_text, round(duration, 1), model),
        )
        row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_history(limit: int = 100, offset: int = 0, db_path: Path | str | None = None) -> list[dict]:
    """Fetch transcription history, most recent first."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT id, raw_text, cleaned_text, duration_seconds, whisper_model, timestamp FROM transcriptions ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_transcription(row_id: int, db_path: Path | str | None = None) -> None:
    conn = _connect(db_path)
    with conn:
        conn.execute("DELETE FROM transcriptions WHERE id = ?", (row_id,))
    conn.close()


def clear_history(db_path: Path | str | None = None) -> None:
    conn = _connect(db_path)
    with conn:
        conn.execute("DELETE FROM transcriptions")
    conn.close()


def get_stats(db_path: Path | str | None = None) -> dict:
    """Calculate usage stats using SQL aggregations: total transcriptions, word count, duration, and time saved."""
    conn = _connect(db_path)
    summary = conn.execute("""
        SELECT 
            COUNT(*) as total_count,
            COALESCE(SUM(duration_seconds), 0.0) as total_duration
        FROM transcriptions
    """).fetchone()

    rows = conn.execute("SELECT cleaned_text FROM transcriptions").fetchall()
    conn.close()

    total_count = summary["total_count"] if summary else 0
    total_duration = summary["total_duration"] if summary else 0.0

    total_words = 0
    for row in rows:
        text = row["cleaned_text"] or ""
        total_words += len(text.split())

    # Average typing speed: 40 WPM. Average speaking: 150 WPM.
    # Time saved = words * (1/40 - 1/150) min = words * 0.01833 min.
    time_saved_minutes = round(total_words * 0.01833, 1)

    return {
        "total_transcriptions": total_count,
        "total_words": total_words,
        "total_duration_seconds": round(total_duration, 1),
        "time_saved_minutes": time_saved_minutes,
    }
