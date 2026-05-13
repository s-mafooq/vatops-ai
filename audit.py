import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "audit.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
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
    # Add session_id column if upgrading existing db
    try:
        c.execute("ALTER TABLE audit_log ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def log_extraction(
    filename: str,
    extracted_data: dict,
    vat_category: str,
    vat_flags: list,
    confidence: float,
    processing_time: float,
    session_id: str = "default"
) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO audit_log (
            session_id, filename, upload_time, extracted_data, vat_category,
            vat_flags, confidence, status, processing_time_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        session_id,
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


def get_all_records(session_id: str = "default") -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM audit_log WHERE session_id = ? ORDER BY upload_time DESC",
        (session_id,)
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_summary_stats(session_id: str = "default") -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM audit_log WHERE session_id = ?", (session_id,))
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE session_id = ? AND status = 'approved'", (session_id,))
    approved = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE session_id = ? AND status = 'rejected'", (session_id,))
    rejected = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM audit_log WHERE session_id = ? AND status = 'pending'", (session_id,))
    pending = c.fetchone()[0]

    c.execute("SELECT AVG(confidence) FROM audit_log WHERE session_id = ?", (session_id,))
    avg_confidence = c.fetchone()[0] or 0.0

    c.execute("SELECT AVG(processing_time_seconds) FROM audit_log WHERE session_id = ?", (session_id,))
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