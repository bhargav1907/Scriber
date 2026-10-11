"""
Scriber — SQLite Database for Transcription History
"""

import sqlite3
from config import DB_FILE


def _connect():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the transcriptions table if it doesn't exist."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
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
    conn.commit()
    conn.close()


def save_transcription(raw_text: str, cleaned_text: str, duration: float, model: str) -> int:
    """Save a transcription and return its ID."""
    conn = _connect()
    cursor = conn.execute(
        "INSERT INTO transcriptions (raw_text, cleaned_text, duration_seconds, whisper_model) VALUES (?, ?, ?, ?)",
        (raw_text, cleaned_text, round(duration, 1), model),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_history(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch transcription history, most recent first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_transcription(row_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM transcriptions WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


def clear_history() -> None:
    conn = _connect()
    conn.execute("DELETE FROM transcriptions")
    conn.commit()
    conn.close()
