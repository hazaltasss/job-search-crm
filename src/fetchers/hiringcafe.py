"""
HiringCafe.com fetcher.

HiringCafe uses an internal POST API at /api/search-jobs.
The endpoint is Cloudflare-protected, so we send browser-like headers.
If the API call fails (403/401), we log a warning and return an empty list —
the GitHub Actions IP may be blocked. In that case, enable Playwright fallback.
"""
from __future__ import annotations
import json
import logging
import time
import hashlib
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

_API_URL = "https://hiring.cafe/api/search-jobs"

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://hiring.cafe",
    "Referer": "https://hiring.cafe/",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Platform": '"macOS"',
}

# Search payloads: Working Student + Intern, Berlin + Germany Remote
_SEARCH_PAYLOADS = [
    # ── Working Student — Berlin ──────────────────────────────────────────────
    {
        "name": "Berlin – Working Student (Software/Data/AI)",
        "payload": {
            "searchQuery": "working student software data ai machine learning",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 50,
        },
    },
    {
        "name": "Berlin – Working Student (QA, Testing & Support)",
        "payload": {
            "searchQuery": "working student QA testing test engineer technical support IT",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 50,
        },
    },
    {
        "name": "Berlin – Werkstudent (DE keyword)",
        "payload": {
            "searchQuery": "werkstudent software entwicklung data",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 50,
        },
    },
    {
        "name": "Berlin – Werkstudent (QA, Test & Support DE)",
        "payload": {
            "searchQuery": "werkstudent QA test testing support IT helpdesk",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 50,
        },
    },
    # ── Internship — Berlin ───────────────────────────────────────────────────
    {
        "name": "Berlin – Internship (Software/Data/AI)",
        "payload": {
            "searchQuery": "internship software engineer data science python",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 1],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 50,
        },
    },
    {
        "name": "Berlin – Internship (QA & Testing)",
        "payload": {
            "searchQuery": "internship QA test quality assurance tester",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 1],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 30,
        },
    },
    {
        "name": "Berlin – Praktikum (DE keyword)",
        "payload": {
            "searchQuery": "praktikum softwareentwicklung data python backend",
            "locations": [
                {"formatted_address": "Berlin, Germany", "types": ["locality"]}
            ],
            "workplaceTypes": ["Onsite", "Hybrid", "Remote"],
            "roleYoeRange": [0, 1],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 30,
        },
    },
    # ── Germany-wide Remote ───────────────────────────────────────────────────
    {
        "name": "Germany Remote – Working Student / Intern (Tech)",
        "payload": {
            "searchQuery": "working student intern software data ai remote",
            "locations": [
                {"formatted_address": "Germany", "types": ["country"]}
            ],
            "workplaceTypes": ["Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 40,
        },
    },
    {
        "name": "Germany Remote – QA & Tech Support",
        "payload": {
            "searchQuery": "working student QA test technical support remote",
            "locations": [
                {"formatted_address": "Germany", "types": ["country"]}
            ],
            "workplaceTypes": ["Remote"],
            "roleYoeRange": [0, 2],
            "dateFetchedPastNDays": 3,
            "sortBy": "date_posted",
            "page": 1,
            "pageSize": 40,
        },
    },
]


def _make_job_id(url: str) -> str:
    return "hc_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_job(raw: dict) -> Job | None:
    """Parse a raw HiringCafe API response dict into a Job object."""
    try:
        url = raw.get("jobUrl") or raw.get("url") or raw.get("apply_url", "")
        if not url:
            return None

        title = raw.get("title") or raw.get("jobTitle", "")
        company = (
            raw.get("company") or
            raw.get("companyName") or
            raw.get("organization", {}).get("name", "Unknown")
        )
        location = raw.get("location") or raw.get("jobLocation", "")
        if isinstance(location, dict):
            location = location.get("address", {}).get("addressLocality", "")
        description = raw.get("description") or raw.get("jobDescription", "")
        posted_at = raw.get("datePosted") or raw.get("posted_at", "")

        return Job(
            job_id=_make_job_id(url),
            source="hiringcafe",
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            posted_at=posted_at,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.warning("Failed to parse HiringCafe job: %s — %s", raw, exc)
        return None


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _post_search(client: httpx.Client, payload: dict) -> list[dict]:
    resp = client.post(_API_URL, json=payload, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code in (401, 403):
        logger.warning(
            "HiringCafe returned %d — Cloudflare blocked this IP. "
            "Consider enabling Playwright mode or running locally.",
            resp.status_code,
        )
        return None
    resp.raise_for_status()
    data = resp.json()
    # API may return {"jobs": [...]} or a direct list
    if isinstance(data, list):
        return data
    return data.get("jobs") or data.get("results") or []


def fetch_jobs() -> list[Job]:
    """
    Fetch working student jobs from HiringCafe.
    Returns a deduplicated list of Job objects.
    """
    all_jobs: list[Job] = []
    seen_urls: set[str] = set()

    with httpx.Client(follow_redirects=True) as client:
        for search in _SEARCH_PAYLOADS:
            logger.info("HiringCafe: searching '%s'", search["name"])
            try:
                raw_jobs = _post_search(client, search["payload"])
            except Exception as exc:
                logger.error("HiringCafe search '%s' failed: %s", search["name"], exc)
                break

            if raw_jobs is None:
                # Cloudflare blocked; avoid wasting time on further attempts
                break

            for raw in raw_jobs:
                job = _parse_job(raw)
                if job and job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

            time.sleep(REQUEST_DELAY)

    logger.info("HiringCafe: fetched %d unique jobs", len(all_jobs))
    return all_jobs
