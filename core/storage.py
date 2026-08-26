"""
SQLite-backed repository of scanned products & inspection history.

Prototype-grade storage: one local file (data/scans.db), no server.
Swap for Postgres/Firebase later without touching the rest of the app —
just reimplement these three functions against the new backend.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.rules import ComplianceResult, FieldResult

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scans.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            scanned_at TEXT NOT NULL,
            is_compliant INTEGER NOT NULL,
            score_pct REAL NOT NULL,
            extracted_text TEXT,
            fields_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_scan(product_name: str, extracted_text: str, result: ComplianceResult) -> int:
    conn = sqlite3.connect(DB_PATH)
    fields_json = json.dumps([f.__dict__ for f in result.fields])
    cur = conn.execute(
        """
        INSERT INTO scans (product_name, scanned_at, is_compliant, score_pct, extracted_text, fields_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            product_name,
            datetime.now().isoformat(timespec="seconds"),
            int(result.is_compliant),
            result.score_pct,
            extracted_text,
            fields_json,
        ),
    )
    conn.commit()
    scan_id = cur.lastrowid
    conn.close()
    return scan_id


def list_scans(search: str | None = None) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if search:
        rows = conn.execute(
            "SELECT * FROM scans WHERE product_name LIKE ? ORDER BY scanned_at DESC",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM scans ORDER BY scanned_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scan(scan_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
