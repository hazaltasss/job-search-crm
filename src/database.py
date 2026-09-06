"""
SQLite database wrapper for job deduplication and status tracking.
"""
import sqlite3
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Generator, Optional

import json
import uuid

from src.config import DB_PATH, MASTER_CV_PATH
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
    norm_company TEXT DEFAULT '',
    norm_title   TEXT DEFAULT '',
    sheet_row   INTEGER,
    created_at  TEXT NOT NULL,
    UNIQUE(source, job_id)
);
"""

_CREATE_PROFILES_TABLE = """
CREATE TABLE IF NOT EXISTS profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    headline    TEXT DEFAULT '',
    data_json   TEXT NOT NULL,
    is_active   INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
"""
_CREATE_DEDUP_INDEX = """
CREATE INDEX IF NOT EXISTS idx_dedup_norm ON jobs(norm_company, norm_title);
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


import re

def normalize_company(name: str) -> str:
    """Normalize company name by removing entity forms and extra formatting."""
    if not name:
        return ""
    s = name.lower().strip()
    # Remove corporate suffixes and annotations
    suffixes = [
        r"\(yc\s+s\d+\)",
        r"\(all genders\)",
        r"\|\s*b\s*corp",
        r"\bgmbh\b",
        r"\bag\b",
        r"\bse\b",
        r"\binc\.?\b",
        r"\bincorporated\b",
        r"\bcorp\.?\b",
        r"\bgroup\b",
        r"\bltd\.?\b",
        r"\blimited\b",
        r"\btechnologies\b",
    ]
    for suf in suffixes:
        s = re.sub(suf, "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())


def normalize_title(title: str) -> str:
    """Normalize job title by removing gender suffixes and punctuation."""
    if not title:
        return ""
    s = title.lower().strip()
    # Remove gender suffixes like (m/f/d), (m/w/d), (f/m/x), etc.
    s = re.sub(r"\((m/f/d|f/m/d|m/w/d|f/m/x|m/f/x|d/f/m|f/m/div|all genders)\)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())


# ─── Initialise & Migrate ─────────────────────────────────────────────────────
def init_db() -> None:
    """Create the database schema if it doesn't exist, and run safe column migrations."""
    with _connection() as conn:
        conn.execute(_CREATE_JOBS_TABLE)
        conn.execute(_CREATE_PROFILES_TABLE)
        conn.execute(_CREATE_INDEX)
        # Safe migration for new columns on existing databases
        for col, col_type in [
            ("applied_at", "TEXT DEFAULT ''"),
            ("email_notes", "TEXT DEFAULT ''"),
            ("norm_company", "TEXT DEFAULT ''"),
            ("norm_title", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type};")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Backfill existing rows that have empty norm_company or norm_title
        rows = conn.execute(
            "SELECT id, company, title FROM jobs WHERE (norm_company = '' OR norm_company IS NULL) OR (norm_title = '' OR norm_title IS NULL)"
        ).fetchall()
        for r in rows:
            nc = normalize_company(r["company"] or "")
            nt = normalize_title(r["title"] or "")
            conn.execute(
                "UPDATE jobs SET norm_company = ?, norm_title = ? WHERE id = ?",
                (nc, nt, r["id"]),
            )

        conn.execute(_CREATE_DEDUP_INDEX)
    logger.info("Database initialised at %s", DB_PATH)


# ─── Deduplication ────────────────────────────────────────────────────────────
def is_duplicate(url: str, title: str = "", company: str = "") -> bool:
    """
    Return True if a job with this URL or a matching (company, title) already exists.
    Supports cross-platform duplicate detection using indexed normalized columns.
    """
    with _connection() as conn:
        # Fast path: exact URL match
        if conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone():
            return True

        if not title or not company:
            return False

        norm_c = normalize_company(company)
        norm_t = normalize_title(title)
        if not norm_c or not norm_t:
            return False

        # Indexed lookup — O(1) instead of O(n)
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE norm_title = ? AND norm_company = ?",
            (norm_t, norm_c),
        ).fetchone()
        if row:
            return True

        # Fuzzy: one company name is a substring of the other (scoped to same normalized title)
        rows = conn.execute(
            "SELECT norm_company FROM jobs WHERE norm_title = ?",
            (norm_t,),
        ).fetchall()
        for r in rows:
            ex_c = r["norm_company"] or ""
            if (len(norm_c) >= 4 and norm_c in ex_c) or (len(ex_c) >= 4 and ex_c in norm_c):
                return True

    return False


# ─── Insert ───────────────────────────────────────────────────────────────────
def insert_job(job: Job) -> int:
    """
    Insert a new job into the database.
    Returns the new row's db_id. Raises IntegrityError on duplicates.
    """
    now = datetime.now(timezone.utc).isoformat()
    norm_c = normalize_company(job.company)
    norm_t = normalize_title(job.title)
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs
                (job_id, source, title, company, location, url, language,
                 is_remote, is_berlin, category, match_score, description,
                 posted_at, fetched_at, status, sheet_row, norm_company, norm_title, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job.job_id, job.source, job.title, job.company,
                job.location, job.url, job.language,
                int(job.is_remote), int(job.is_berlin),
                job.category, job.match_score, job.description,
                job.posted_at, job.fetched_at, job.status,
                job.sheet_row, norm_c, norm_t, now,
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


# ─── Profiles Management ───────────────────────────────────────────────────────
DEFAULT_PROFILE_ID = "default_hazal"


def ensure_default_profile(cv_data: dict | None = None) -> str:
    """
    Ensure the default Hazal Taş profile exists in the database.
    If missing or empty, populates it from data/master_cv.json or the provided cv_data.
    """
    with _connection() as conn:
        row = conn.execute("SELECT id, data_json FROM profiles WHERE id = ?", (DEFAULT_PROFILE_ID,)).fetchone()
        master_cv = None
        if MASTER_CV_PATH.exists():
            try:
                with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
                    master_cv = json.load(f)
            except Exception:
                master_cv = None

        if not row:
            data_to_save = cv_data if cv_data is not None else (master_cv or {})
            name = data_to_save.get("personal", {}).get("name", "Hazal Taş")
            headline = "M.Sc. Data Analytics & AI | Computer Engineer"
            conn.execute(
                """
                INSERT INTO profiles (id, name, headline, data_json, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (DEFAULT_PROFILE_ID, name, headline, json.dumps(data_to_save, ensure_ascii=False)),
            )
            logger.info("Created default profile: %s", DEFAULT_PROFILE_ID)
        elif cv_data is not None:
            name = cv_data.get("personal", {}).get("name", "Hazal Taş")
            headline = "M.Sc. Data Analytics & AI | Computer Engineer"
            conn.execute(
                "UPDATE profiles SET name = ?, headline = ?, data_json = ? WHERE id = ?",
                (name, headline, json.dumps(cv_data, ensure_ascii=False), DEFAULT_PROFILE_ID),
            )
        elif master_cv and len(row["data_json"]) < 300:
            name = master_cv.get("personal", {}).get("name", "Hazal Taş")
            headline = "M.Sc. Data Analytics & AI | Computer Engineer"
            conn.execute(
                "UPDATE profiles SET name = ?, headline = ?, data_json = ? WHERE id = ?",
                (name, headline, json.dumps(master_cv, ensure_ascii=False), DEFAULT_PROFILE_ID),
            )
    return DEFAULT_PROFILE_ID


def get_profiles() -> list[dict]:
    """Return all profiles ordered by is_active DESC, created_at ASC."""
    ensure_default_profile()
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, headline, data_json, is_active, created_at, updated_at
            FROM profiles
            ORDER BY is_active DESC, created_at ASC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["data"] = json.loads(d["data_json"])
            except Exception:
                d["data"] = {}
            result.append(d)
        return result


def get_active_profile() -> dict:
    """Return the currently active profile. Defaults to default_hazal if none is active."""
    ensure_default_profile()
    with _connection() as conn:
        row = conn.execute(
            "SELECT id, name, headline, data_json, is_active, created_at, updated_at FROM profiles WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        if not row:
            conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (DEFAULT_PROFILE_ID,))
            row = conn.execute(
                "SELECT id, name, headline, data_json, is_active, created_at, updated_at FROM profiles WHERE id = ?",
                (DEFAULT_PROFILE_ID,),
            ).fetchone()

        d = dict(row)
        try:
            d["data"] = json.loads(d["data_json"])
        except Exception:
            d["data"] = {}
        return d


def set_active_profile(profile_id: str) -> bool:
    """Set the specified profile as the active one."""
    with _connection() as conn:
        exists = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not exists:
            return False
        conn.execute("UPDATE profiles SET is_active = 0")
        conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (profile_id,))
        return True


def save_profile(name: str, headline: str, data: dict, profile_id: str | None = None) -> str:
    """Insert or update a profile record and return its ID."""
    if not profile_id:
        profile_id = f"prof_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    json_str = json.dumps(data, ensure_ascii=False)
    with _connection() as conn:
        existing = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE profiles
                SET name = ?, headline = ?, data_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, headline, json_str, now, profile_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO profiles (id, name, headline, data_json, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (profile_id, name, headline, json_str, now, now),
            )
    return profile_id


def delete_profile(profile_id: str) -> bool:
    """Delete a profile. Default profile cannot be deleted."""
    if profile_id == DEFAULT_PROFILE_ID:
        return False
    with _connection() as conn:
        row = conn.execute("SELECT is_active FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return False
        was_active = bool(row["is_active"])
        conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        if was_active:
            conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (DEFAULT_PROFILE_ID,))
        return True
