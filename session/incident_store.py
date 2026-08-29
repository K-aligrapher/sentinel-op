"""Persistent incident history in SQLite (WAL mode, 30s busy timeout)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    incident_type TEXT,
    pod           TEXT,
    namespace     TEXT,
    rca_summary   TEXT,
    proposed_fix  TEXT,
    fix_applied   TEXT,
    decision      TEXT,
    resolved      INTEGER DEFAULT 0,
    full_data     TEXT
)
"""


def _db_path() -> str:
    """Resolve the SQLite path from $SESSION_DB_PATH at call time."""
    return os.getenv("SESSION_DB_PATH", "./logs/incidents.db")


def _timeout_s() -> float:
    """SQLite busy timeout in seconds from $SQLITE_TIMEOUT_SECONDS (default 30)."""
    return float(os.getenv("SQLITE_TIMEOUT_SECONDS", "30"))


def _now() -> str:
    """Current UTC timestamp in ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open the incident DB in WAL mode with a busy timeout and ensure the schema exists."""
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=_timeout_s())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_SCHEMA)
    return conn


def save_incident(incident_id: str, results: dict) -> None:
    """Insert or replace the incident row, preserving any prior decision / resolved state."""
    rca = results.get("rca", {}) or {}
    with _connect() as conn:
        prior = conn.execute(
            "SELECT decision, resolved, fix_applied FROM incidents WHERE id=?", (incident_id,)
        ).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                incident_id, _now(), results.get("incident_type", "unknown"),
                results.get("pod", ""), results.get("namespace", ""),
                (rca.get("summary", "") or "")[:500], rca.get("proposed_fix", ""),
                prior["fix_applied"] if prior else "",
                prior["decision"] if prior else "",
                prior["resolved"] if prior else 0,
                json.dumps(results, default=str),
            ),
        )
    log.info("session.saved", incident_id=incident_id)


def mark_resolved(incident_id: str, fix_applied: str, decision: str, resolved: bool) -> None:
    """Record the human decision and whether the alert cleared after the fix."""
    with _connect() as conn:
        conn.execute(
            "UPDATE incidents SET fix_applied=?, decision=?, resolved=? WHERE id=?",
            (fix_applied, decision, 1 if resolved else 0, incident_id),
        )
    log.info("session.updated", incident_id=incident_id, decision=decision, resolved=resolved)


def load_incident(incident_id: str) -> dict | None:
    """Return the incident row as a dict, or None if the id is unknown (never raises)."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
    return dict(row) if row else None


def get_recent(n: int = 10) -> list[dict]:
    """Return up to n incidents newest-first; an empty list when n <= 0."""
    if n <= 0:
        return []
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM incidents ORDER BY created_at DESC, id DESC LIMIT ?", (n,)
        )]


def next_incident_id() -> str:
    """Generate the next INC-YYYY-NNN id from the current year's row count."""
    year = datetime.now(timezone.utc).year
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE created_at LIKE ?", (f"{year}%",)
        ).fetchone()[0]
    return f"INC-{year}-{count + 1:03d}"
