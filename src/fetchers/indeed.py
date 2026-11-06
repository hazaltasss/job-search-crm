"""
Indeed Germany job fetcher using python-jobspy.

Scrapes public Indeed job listings in Germany without requiring credentials.
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
    TARGET_LOCATIONS,
)

logger = logging.getLogger(__name__)


def _build_search_queries() -> list[dict]:
    primary_loc = TARGET_LOCATIONS[0] if TARGET_LOCATIONS else "Berlin"
    if "germany" not in primary_loc.lower() and "remote" not in primary_loc.lower():
        primary_loc = f"{primary_loc}, Germany"

    return [
        {"search_term": "working student data ai", "location": primary_loc, "results_wanted": 25},
        {"search_term": "working student software developer", "location": primary_loc, "results_wanted": 25},
        {"search_term": "internship data python", "location": primary_loc, "results_wanted": 20},
    ]


_SEARCH_QUERIES = _build_search_queries()


def _make_job_id(job_url: str) -> str:
    return "ind_" + hashlib.md5(job_url.encode("utf-8")).hexdigest()[:12]


def _is_relevant_position(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    for pattern in WORKING_STUDENT_PATTERNS + INTERN_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False


def _parse_jobspy_row(row: dict, now_iso: str) -> Optional[Job]:
    try:
        job_url = str(row.get("job_url") or row.get("job_url_direct") or "").strip()
        if not job_url or not job_url.startswith("http"):
            return None

        title = str(row.get("title") or "").strip()
        if not title:
            return None

        if not _is_relevant_position(title):
            logger.debug("Skipping non-student/intern Indeed title: %s", title)
            return None

        company = str(row.get("company") or row.get("company_name") or "").strip() or "Unknown"
        raw_loc = str(row.get("location") or "").strip()
        description = str(row.get("description") or "").strip()
        if raw_loc:
            location = raw_loc
        else:
            location = "Berlin, Germany" if "berlin" in description.lower() else "Germany"

        is_remote_flag = bool(row.get("is_remote", False))
        loc_lower = location.lower()
        is_remote = is_remote_flag or any(kw in loc_lower for kw in REMOTE_KEYWORDS)
        is_berlin = any(kw in loc_lower for kw in BERLIN_KEYWORDS)

        posted_at_val = row.get("date_posted")
        posted_at = str(posted_at_val) if posted_at_val is not None and not pd.isna(posted_at_val) else ""

        return Job(
            job_id=_make_job_id(job_url),
            source="indeed",
            title=title,
            company=company,
            location=location,
            url=job_url,
            description=description,
            language="en",
            is_remote=is_remote,
            is_berlin=is_berlin,
            posted_at=posted_at,
            fetched_at=now_iso,
        )
    except Exception as exc:
        logger.warning("Error parsing Indeed job row: %s", exc)
        return None


def fetch_jobs(
    hours_old: int = 72,
    queries: Optional[list[dict]] = None,
) -> list[Job]:
    target_queries = queries or _SEARCH_QUERIES
    now_iso = datetime.now(timezone.utc).isoformat()
    from concurrent.futures import ThreadPoolExecutor, as_completed

    seen_urls: set[str] = set()
    collected_jobs: list[Job] = []

    def _run_single_query(q: dict) -> list[Job]:
        search_term = q["search_term"]
        location = q["location"]
        results_wanted = q.get("results_wanted", 20)

        logger.info("Indeed querying: '%s' in '%s' (wanted: %d)", search_term, location, results_wanted)
        try:
            df = scrape_jobs(
                site_name=["indeed"],
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed="germany",
                user_agent=USER_AGENT,
                verbose=0,
            )
            if df is None or df.empty:
                logger.info("Indeed '%s': 0 raw results", search_term)
                return []

            batch_jobs: list[Job] = []
            for _, r in df.iterrows():
                j = _parse_jobspy_row(r.to_dict(), now_iso)
                if j and j.url not in seen_urls:
                    seen_urls.add(j.url)
                    batch_jobs.append(j)

            logger.info("Indeed '%s': %d valid student/intern jobs parsed", search_term, len(batch_jobs))
            return batch_jobs
        except Exception as exc:
            logger.error("Indeed query '%s' failed: %s", search_term, exc)
            return []

    with ThreadPoolExecutor(max_workers=min(len(target_queries), 3)) as pool:
        futures = {pool.submit(_run_single_query, q): q for q in target_queries}
        for fut in as_completed(futures):
            try:
                res = fut.result()
                collected_jobs.extend(res)
            except Exception as e:
                logger.error("Indeed worker failed: %s", e)

    unique_jobs: list[Job] = []
    seen_ids: set[str] = set()
    for job in collected_jobs:
        if job.job_id not in seen_ids:
            seen_ids.add(job.job_id)
            unique_jobs.append(job)

    logger.info("Indeed total collected: %d unique student/intern jobs", len(unique_jobs))
    return unique_jobs
