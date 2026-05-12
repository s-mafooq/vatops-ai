import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "audit.db")


def init_db():
    """Create the audit table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            extracted_data TEXT,
            vat_category TEXT,
            vat_flags TEXT,
            confidence REAL,
            status TEXT DEFAULT 'pending',
            user_edits TEXT,
            approved_data TEXT,
            approved_time TEXT,
            processing_time_seconds REAL,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_extraction(
    filename: str,
    extracted_data: dict,
    vat_category: str,
    vat_flags: list,
    confidence: float,
    processing_time: float
) -> int:
    """
    Log a new extraction. Returns the row ID for later updates.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO audit_log (
            filename, upload_time, extracted_data, vat_category,
            vat_flags, confidence, status, processing_time_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        filename,
        datetime.now().isoformat(),
        json.dumps(extracted_data),
        vat_category,
        json.dumps(vat_flags),
        confidence,
        processing_time
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def log_approval(row_id: int, approved_data: dict, user_edits: dict):
    """Mark a record as approved with final data and any edits made."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE audit_log
        SET status = 'approved',
            approved_data = ?,
            user_edits = ?,
            approved_time = ?
        WHERE id = ?
    """, (
        json.dumps(approved_data),
        json.dumps(user_edits),
        datetime.now().isoformat(),
        row_id
    ))
    conn.commit()
    conn.close()


def log_rejection(row_id: int, reason: str = ""):
    """Mark a record as rejected."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE audit_log
        SET status = 'rejected',
            notes = ?,
            approved_time = ?
        WHERE id = ?
    """, (reason, datetime.now().isoformat(), row_id))
    conn.commit()
    conn.close()


def get_all_records() -> list[dict]:
    """Fetch all audit records as a list of dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM audit_log ORDER BY upload_time DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_summary_stats() -> dict:
    """Return headline stats for the dashboard."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM audit_log")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE status = 'approved'")
    approved = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE status = 'rejected'")
    rejected = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE status = 'pending'")
    pending = c.fetchone()[0]

    c.execute("SELECT AVG(confidence) FROM audit_log")
    avg_confidence = c.fetchone()[0] or 0.0

    c.execute("SELECT AVG(processing_time_seconds) FROM audit_log")
    avg_time = c.fetchone()[0] or 0.0

    conn.close()

    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "avg_confidence": round(avg_confidence * 100, 1),
        "avg_processing_time": round(avg_time, 1),
        "auto_approval_rate": round((approved / total * 100), 1) if total > 0 else 0.0
    }