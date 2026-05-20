"""
Event publisher for pdf2xls-generator.

Writes events to a shared SQLite database that routine-analyzer reads on startup.
This replaces the previous subprocess.run() call, so neither project depends
on the other's file path or Python environment.

Usage:
    from helpers.events import publish_event
    publish_event("run:new-routine")
    publish_event("run:global")
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from training_shared.events import EventType  # shared constants — no magic strings

DB_PATH = Path(__file__).parent.parent.parent.parent / "events.db"


def _get_connection():
    """Open (or create) the SQLite database and ensure the events table exists."""
    conn = sqlite3.connect(DB_PATH)

    # CREATE TABLE IF NOT EXISTS is safe to run on every connection.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type   TEXT    NOT NULL,
            payload      TEXT,
            created_at   TEXT    NOT NULL,
            processed_at TEXT
        )
    """)
    conn.commit()
    return conn


def publish_event(event_type, payload=None):
    """
    Insert a new pending event into the queue.

    Args:
        event_type: String identifier, e.g. "run:new-routine".
        payload:    Optional JSON string with extra data (not used yet).

    Example:
        publish_event("run:new-routine")
    """
    conn = _get_connection()
    now  = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO events (event_type, payload, created_at) VALUES (?, ?, ?)",
        (event_type, payload, now)
    )
    conn.commit()
    conn.close()
    print(f"[events] Published: {event_type}")
