
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "swasthiq.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestions (
    clinic_id TEXT NOT NULL,
    log_date TEXT NOT NULL,
    raw_log TEXT NOT NULL,
    reconciliation_report TEXT NOT NULL,
    analytics_report TEXT NOT NULL,
    rejected_row_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (clinic_id, log_date)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def save_ingestion(
    clinic_id: str,
    log_date: str,
    raw_log: list,
    reconciliation_report: dict,
    analytics_report: dict,
    rejected_row_count: int,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ingestions
                (clinic_id, log_date, raw_log, reconciliation_report, analytics_report,
                 rejected_row_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(clinic_id, log_date) DO UPDATE SET
                raw_log = excluded.raw_log,
                reconciliation_report = excluded.reconciliation_report,
                analytics_report = excluded.analytics_report,
                rejected_row_count = excluded.rejected_row_count,
                updated_at = datetime('now')
            """,
            (
                clinic_id,
                log_date,
                json.dumps(raw_log),
                json.dumps(reconciliation_report),
                json.dumps(analytics_report),
                rejected_row_count,
            ),
        )


def get_ingestion(clinic_id: str, log_date: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ingestions WHERE clinic_id = ? AND log_date = ?",
            (clinic_id, log_date),
        ).fetchone()
        if row is None:
            return None
        return {
            "clinic_id": row["clinic_id"],
            "log_date": row["log_date"],
            "raw_log": json.loads(row["raw_log"]),
            "reconciliation_report": json.loads(row["reconciliation_report"]),
            "analytics_report": json.loads(row["analytics_report"]),
            "rejected_row_count": row["rejected_row_count"],
            "updated_at": row["updated_at"],
        }


def list_ingestions() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT clinic_id, log_date, rejected_row_count, updated_at FROM ingestions "
            "ORDER BY log_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
