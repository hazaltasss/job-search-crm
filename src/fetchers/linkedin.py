"""
LinkedIn job fetcher using python-jobspy.

Scrapes public LinkedIn job listings without requiring credentials or session cookies.
Filters specifically for Werkstudent (Working Student) and Internship positions
in Berlin and Remote Germany across Data, AI, and Software Engineering domains.
"""
from __future__ import annotations
import re
import time
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from jobspy import scrape_jobs
import pandas as pd

from src.models import Job
from src.config import (
    USER_AGENT,
    BERLIN_KEYWORDS,
    REMOTE_KEYWORDS,
    WORKING_STUDENT_PATTERNS,
    INTERN_PATTERNS,
)

logger = logging.getLogger(__name__)

# Targeted search queries aligned with Hazal's profile & criteria
_SEARCH_QUERIES = [
    {
        "search_term": "working student data science machine learning",
        "location": "Berlin, Germany",
        "results_wanted": 25,
    },
    {
        "search_term": "working student software engineer python",
        "location": "Berlin, Germany",
        "results_wanted": 25,
    },
    {
        "search_term": "internship data science software engineer",
        "location": "Berlin, Germany",
        "results_wanted": 25,
    },
    {
        "search_term": "working student remote data software",
        "location": "Germany",
        "results_wanted": 20,
    },
]


def _make_job_id(job_url: str) -> str:
    """Generate a deterministic unique ID for a LinkedIn job URL."""
    return "li_" + hashlib.md5(job_url.encode("utf-8")).hexdigest()[:12]


def _is_relevant_position(title: str) -> bool:
    """Ensure title explicitly matches working student or internship patterns."""
    if not title:
        return False
    t = title.lower()
    for pattern in WORKING_STUDENT_PATTERNS + INTERN_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False


def _parse_jobspy_row(row: dict, now_iso: str) -> Optional[Job]:
    """Convert a single JobSpy DataFrame row into a Job dataclass instance."""
    try:
        job_url = str(row.get("job_url") or "").strip()
        if not job_url or not job_url.startswith("http"):
            return None

        title = str(row.get("title") or "").strip()
        if not title:
            return None

        if not _is_relevant_position(title):
            logger.debug("Skipping non-student/intern title: %s", title)
            return None

        company = str(row.get("company") or row.get("company_name") or "").strip() or "Unknown"
        location = str(row.get("location") or "Berlin, Germany").strip()
        description = str(row.get("description") or "").strip()

        is_remote_flag = bool(row.get("is_remote", False))
        loc_lower = location.lower()
        is_remote = is_remote_flag or any(kw in loc_lower for kw in REMOTE_KEYWORDS)
        is_berlin = any(kw in loc_lower for kw in BERLIN_KEYWORDS)

        posted_at_val = row.get("date_posted")
        posted_at = str(posted_at_val) if posted_at_val is not None and not pd.isna(posted_at_val) else ""

        return Job(
            job_id=_make_job_id(job_url),
            source="linkedin",
            title=title,
            company=company,
            location=location,
            url=job_url,
            description=description,
            language="en",  # will be verified by language filter pipeline
            is_remote=is_remote,
            is_berlin=is_berlin,
            posted_at=posted_at,
            fetched_at=now_iso,
        )
    except Exception as exc:
        logger.warning("Error parsing LinkedIn job row: %s", exc)
        return None


def fetch_jobs(
    hours_old: int = 72,
    queries: Optional[list[dict]] = None,
) -> list[Job]:
    """
    Fetch jobs from LinkedIn using python-jobspy across targeted search queries.

    Args:
        hours_old: Lookback window in hours (default 72 hours).
        queries: Optional custom queries list, defaults to _SEARCH_QUERIES.

    Returns:
        List of deduplicated Job objects matching working student/intern criteria.
    """
    target_queries = queries or _SEARCH_QUERIES
    now_iso = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    collected_jobs: list[Job] = []

    logger.info("Starting LinkedIn fetch across %d queries...", len(target_queries))

    for idx, q in enumerate(target_queries, start=1):
        search_term = q["search_term"]
        location = q["location"]
        results_wanted = q.get("results_wanted", 20)

        logger.info(
            "LinkedIn query [%d/%d]: '%s' in '%s' (wanted: %d)",
            idx, len(target_queries), search_term, location, results_wanted,
        )

        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                linkedin_fetch_description=True,
                user_agent=USER_AGENT,
                verbose=0,
            )
        except Exception as exc:
            logger.error("LinkedIn scrape failed for '%s': %s", search_term, exc)
            continue

        if df is None or df.empty:
            logger.info("LinkedIn query '%s' returned 0 results.", search_term)
            time.sleep(1.0)
            continue

        query_jobs_count = 0
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            job = _parse_jobspy_row(row_dict, now_iso)
            if job and job.url not in seen_urls:
                seen_urls.add(job.url)
                collected_jobs.append(job)
                query_jobs_count += 1

        logger.info(
            "LinkedIn query '%s': %d total returned, %d relevant student/intern jobs kept",
            search_term, len(df), query_jobs_count,
        )

        # Politeness sleep between queries
        time.sleep(1.0)

    logger.info(
        "LinkedIn fetch complete: %d unique relevant jobs collected.",
        len(collected_jobs),
    )
    return collected_jobs
