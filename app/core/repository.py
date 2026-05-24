"""
State repository. SQLite locally, swap the engine URL for Postgres/Cloud SQL
on GCP. Nothing else in the codebase touches the DB directly — only this file.
This keeps the local->cloud migration to a single line change.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core import event_bus
from app.core.schemas import StatusEvent

DB_PATH = os.environ.get("DB_PATH", "/data/ops.db")


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    _ensure_parent(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS tickets (
                request_id TEXT PRIMARY KEY,
                channel TEXT,
                raw_text TEXT,
                category TEXT,
                urgency TEXT,
                sentiment TEXT,
                decision TEXT,
                payload_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                node TEXT,
                status TEXT,
                detail TEXT,
                at TEXT
            );
            """
        )


def upsert_ticket(request_id: str, **fields) -> None:
    payload = json.dumps(fields.pop("payload", {}), default=str)
    cols = ["request_id", "payload_json", *fields.keys()]
    vals = [request_id, payload, *fields.values()]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "request_id")
    with _conn() as c:
        c.execute(
            f"INSERT INTO tickets ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(request_id) DO UPDATE SET {updates}",
            vals,
        )


def record_event(ev: StatusEvent) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO status_events (request_id, node, status, detail, at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ev.request_id, ev.node, ev.status, ev.detail, ev.at.isoformat()),
        )
    event_bus.publish(ev)


def events_for(request_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT node, status, detail, at FROM status_events WHERE request_id=? ORDER BY id",
            (request_id,),
        ).fetchall()
    return [dict(r) for r in rows]
