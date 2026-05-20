"""Tests for the event publisher (pdf2xls-generator side)."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    # Don't create the table — publisher must create it itself
    return Path(tmp.name)


def _fetch_all(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM events").fetchall()
    conn.close()
    return rows


def test_publish_event_inserts_row():
    db = _make_temp_db()

    with patch("helpers.events.events.DB_PATH", db):
        from helpers.events.events import publish_event
        publish_event("run:new-routine")

    rows = _fetch_all(db)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "run:new-routine"
    assert rows[0]["processed_at"] is None


def test_publish_event_creates_table_if_missing():
    """Publisher must initialise the DB schema on first use."""
    db = _make_temp_db()

    with patch("helpers.events.events.DB_PATH", db):
        from helpers.events.events import publish_event
        publish_event("run:global")  # should not raise

    rows = _fetch_all(db)
    assert len(rows) == 1


def test_publish_multiple_events():
    db = _make_temp_db()

    with patch("helpers.events.events.DB_PATH", db):
        from helpers.events.events import publish_event
        publish_event("run:global")
        publish_event("run:monthly")
        publish_event("run:new-routine")

    rows = _fetch_all(db)
    types = [r["event_type"] for r in rows]
    assert types == ["run:global", "run:monthly", "run:new-routine"]


def test_publish_event_with_payload():
    db = _make_temp_db()

    with patch("helpers.events.events.DB_PATH", db):
        from helpers.events.events import publish_event
        publish_event("run:new-routine", payload='{"sheet": "2026-05"}')

    rows = _fetch_all(db)
    assert rows[0]["payload"] == '{"sheet": "2026-05"}'


def test_published_event_has_created_at():
    db = _make_temp_db()

    with patch("helpers.events.events.DB_PATH", db):
        from helpers.events.events import publish_event
        publish_event("run:global")

    rows = _fetch_all(db)
    assert rows[0]["created_at"] is not None
    assert "T" in rows[0]["created_at"]  # ISO 8601 format
