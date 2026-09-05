"""
SQLite database wrapper for job deduplication and status tracking.
"""
import sqlite3
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Generator, Optional

from src.config import DB_PATH
from src.models import Job

logger = logging.getLogger(__name__)


# ─── Schema ───────────────────────────────────────────────────────────────────
_CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT,
    location    TEXT,
    url         TEXT UNIQUE NOT NULL,
    language    TEXT DEFAULT 'unknown',
    is_remote   INTEGER DEFAULT 0,
    is_berlin   INTEGER DEFAULT 0,
    category    TEXT DEFAULT '',
    match_score INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    posted_at   TEXT DEFAULT '',
    fetched_at  TEXT NOT NULL,
    status      TEXT DEFAULT 'new',
    applied_at  TEXT DEFAULT '',
    email_notes TEXT DEFAULT '',
    sheet_row   INTEGER,
    created_at  TEXT NOT NULL,
    UNIQUE(source, job_id)
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
"""


# ─── Context Manager ──────────────────────────────────────────────────────────
@contextmanager
def _connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Initialise & Migrate ─────────────────────────────────────────────────────
def init_db() -> None:
    """Create the database schema if it doesn't exist, and run safe column migrations."""
    with _connection() as conn:
        conn.execute(_CREATE_JOBS_TABLE)
        conn.execute(_CREATE_INDEX)
        # Safe migration for new columns on existing databases
        for col, col_type in [("applied_at", "TEXT DEFAULT ''"), ("email_notes", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type};")
            except sqlite3.OperationalError:
                pass  # Column already exists
    logger.info("Database initialised at %s", DB_PATH)


# ─── Deduplication ────────────────────────────────────────────────────────────
def is_duplicate(url: str) -> bool:
    """Return True if a job with this URL already exists in the database."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE url = ?", (url,)
        ).fetchone()
    return row is not None


# ─── Insert ───────────────────────────────────────────────────────────────────
def insert_job(job: Job) -> int:
    """
    Insert a new job into the database.
    Returns the new row's db_id. Raises IntegrityError on duplicates.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs
                (job_id, source, title, company, location, url, language,
                 is_remote, is_berlin, category, match_score, description,
                 posted_at, fetched_at, status, sheet_row, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job.job_id, job.source, job.title, job.company,
                job.location, job.url, job.language,
                int(job.is_remote), int(job.is_berlin),
                job.category, job.match_score, job.description,
                job.posted_at, job.fetched_at, job.status,
                job.sheet_row, now,
            ),
        )
        db_id = cursor.lastrowid
    logger.debug("Inserted job db_id=%s  url=%s", db_id, job.url)
    return db_id


# ─── Update ───────────────────────────────────────────────────────────────────
def update_status(db_id: int, status: str, applied_date: Optional[str] = None) -> None:
    """
    Update the status of a job row (e.g. 'applied', 'interview', 'rejected', 'skipped', 'saved').
    If status is 'applied', automatically sets applied_at timestamp if not already set.
    """
    now_date = applied_date or datetime.now(timezone.utc).isoformat()[:10]
    with _connection() as conn:
        if status == "applied":
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    applied_at = CASE WHEN (applied_at IS NULL OR applied_at = '') THEN ? ELSE applied_at END
                WHERE id = ?
                """,
                (status, now_date, db_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?", (status, db_id)
            )
    logger.info("Updated job db_id=%s  status=%s", db_id, status)


def update_job_from_email(db_id: int, new_status: str, email_note: str) -> None:
    """Update job status and append notes from Gmail sync."""
    with _connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, email_notes = ?
            WHERE id = ?
            """,
            (new_status, email_note, db_id),
        )
    logger.info("Email sync updated job db_id=%s -> %s: %s", db_id, new_status, email_note)


def update_sheet_row(db_id: int, sheet_row: int) -> None:
    """Store the Google Sheets row number once the job is appended."""
    with _connection() as conn:
        conn.execute(
            "UPDATE jobs SET sheet_row = ? WHERE id = ?", (sheet_row, db_id)
        )


# ─── Queries ──────────────────────────────────────────────────────────────────
def get_job_by_db_id(db_id: int) -> Optional[dict]:
    """Return a single job row as a dict, or None."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (db_id,)
        ).fetchone()
    return dict(row) if row else None


def get_applied_jobs() -> list[dict]:
    """Return all jobs that have been applied to, ordered by application date."""
    query = """
        SELECT * FROM jobs
        WHERE status IN ('applied', 'interview', 'rejected', 'assessment')
        ORDER BY CASE WHEN (applied_at IS NOT NULL AND applied_at != '') THEN applied_at ELSE created_at END DESC
    """
    with _connection() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(r) for r in rows]


def find_job_by_company(company_name: str) -> Optional[dict]:
    """Find the most recent applied job matching a company name substring."""
    comp = company_name.strip().lower()
    if not comp or len(comp) < 2:
        return None
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE LOWER(company) LIKE ?
               OR LOWER(?) LIKE '%' || LOWER(company) || '%'
            ORDER BY id DESC
            """,
            (f"%{comp}%", comp),
        ).fetchall()
    return dict(rows[0]) if rows else None


def get_all_jobs(status: Optional[str] = None) -> list[dict]:
    """Return all jobs, optionally filtered by status."""
    query = "SELECT * FROM jobs"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC"
    with _connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Return counts grouped by status."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        ).fetchall()
    return {r["status"]: r["count"] for r in rows}


def get_recent_descriptions(days: int = 30) -> list[str]:
    """Return job descriptions from the last N days for analytics."""
    cutoff = datetime.now(timezone.utc).isoformat()[:10]  # YYYY-MM-DD
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT description FROM jobs
            WHERE date(fetched_at) >= date(?, ?)
            AND description != ''
            """,
            (cutoff, f"-{days} days"),
        ).fetchall()
    return [r["description"] for r in rows]
