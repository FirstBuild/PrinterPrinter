import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS print_start_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    printer_id TEXT NOT NULL,
    printer_name TEXT,
    file_name TEXT,
    started_at TEXT,
    eta_end_at TEXT,
    est_duration_sec INTEGER,
    filament_estimated_g REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_event_id)
);

CREATE TABLE IF NOT EXISTS label_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    FOREIGN KEY(event_id) REFERENCES print_start_events(id)
);
"""


def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def upsert_print_start_event(
    db_path: str,
    *,
    source: str,
    source_event_id: str,
    printer_id: str,
    printer_name: str | None,
    file_name: str | None,
    started_at: str | None,
    eta_end_at: str | None,
    est_duration_sec: int | None,
    filament_estimated_g: float | None,
) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            INSERT INTO print_start_events (
                source,
                source_event_id,
                printer_id,
                printer_name,
                file_name,
                started_at,
                eta_end_at,
                est_duration_sec,
                filament_estimated_g
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_event_id) DO NOTHING;
            """,
            (
                source,
                source_event_id,
                printer_id,
                printer_name,
                file_name,
                started_at,
                eta_end_at,
                est_duration_sec,
                filament_estimated_g,
            ),
        )
        inserted = cur.rowcount > 0
        row = conn.execute(
            """
            SELECT id, source, source_event_id, printer_id, printer_name, file_name,
                   started_at, eta_end_at, est_duration_sec, filament_estimated_g, created_at
            FROM print_start_events
            WHERE source = ? AND source_event_id = ?;
            """,
            (source, source_event_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("Failed to fetch event row after upsert")

    return {"inserted": inserted, "event": dict(row)}


def list_recent_print_start_events(db_path: str, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, source, source_event_id, printer_id, printer_name, file_name,
                   started_at, eta_end_at, est_duration_sec, filament_estimated_g, created_at
            FROM print_start_events
            ORDER BY id DESC
            LIMIT ?;
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_print_start_event(db_path: str, event_id: int) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, source, source_event_id, printer_id, printer_name, file_name,
                   started_at, eta_end_at, est_duration_sec, filament_estimated_g, created_at
            FROM print_start_events
            WHERE id = ?;
            """,
            (event_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def record_label_job_attempt(
    db_path: str,
    *,
    event_id: int,
    status: str,
    attempts: int,
    error_message: str | None,
) -> int:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO label_jobs (event_id, status, attempts, error_message, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'));
            """,
            (event_id, status, attempts, error_message),
        )
        conn.commit()
        return int(cur.lastrowid)
