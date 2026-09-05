"""
Arbeitnow.com Job Board API fetcher.

HiringCafe'nin yerine kullanılır — Arbeitnow ücretsiz, public, key gerektirmeyen
bir API sunar ve tam iş ilanı açıklamaları döner.

API: GET https://www.arbeitnow.com/api/job-board-api?page=N
Dökümantasyon: https://www.arbeitnow.com/post/job-board-api
"""
from __future__ import annotations
import logging
import time
import hashlib
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

_API_URL = "https://www.arbeitnow.com/api/job-board-api"

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

# Werkstudent / Intern için arama terimleri (title filtering)
_POSITION_KEYWORDS = [
    "working student", "werkstudent", "intern", "internship",
    "praktikant", "praktikum", "studentische", "student assistant",
]

# Berlin / Remote Germany filtresi
_LOCATION_KEYWORDS = ["berlin", "remote", "germany", "deutschland"]


def _make_job_id(slug: str) -> str:
    return "an_" + hashlib.md5(slug.encode()).hexdigest()[:12]


def _is_relevant_position(title: str, tags: list[str]) -> bool:
    """Sadece Werkstudent/Intern pozisyonları kabul et."""
    text = title.lower() + " " + " ".join(t.lower() for t in tags)
    return any(kw in text for kw in _POSITION_KEYWORDS)


def _is_relevant_location(location: str, is_remote: bool) -> bool:
    """Berlin veya Remote Germany ilanlarını kabul et."""
    if is_remote:
        return True
    loc = location.lower()
    return any(kw in loc for kw in _LOCATION_KEYWORDS)


def _parse_job(raw: dict) -> Job | None:
    try:
        title    = raw.get("title", "")
        company  = raw.get("company_name", "Unknown")
        location = raw.get("location", "")
        url      = raw.get("url", "")
        slug     = raw.get("slug", url)
        desc     = raw.get("description", "")
        tags     = raw.get("tags", [])
        remote   = bool(raw.get("remote", False))
        created  = str(raw.get("created_at", ""))

        if not url or not title:
            return None

        # Pozisyon filtresi
        if not _is_relevant_position(title, tags):
            return None

        # Lokasyon filtresi
        if not _is_relevant_location(location, remote):
            return None

        return Job(
            job_id=_make_job_id(slug),
            source="arbeitnow",
            title=title,
            company=company,
            location=location if location else ("Remote, Germany" if remote else "Germany"),
            url=url,
            description=desc,
            posted_at=created[:10] if created else "",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            is_remote=remote,
        )
    except Exception as exc:
        logger.warning("Arbeitnow parse error: %s — %s", raw.get("title"), exc)
        return None


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _fetch_page(client: httpx.Client, page: int) -> list[dict]:
    resp = client.get(
        _API_URL,
        params={"page": page},
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def fetch_jobs(max_pages: int = 5) -> list[Job]:
    """
    Arbeitnow API'den ilanları çek, Werkstudent/Intern + Berlin/Remote filtrele.
    max_pages: kaç sayfa taransın (her sayfa ~25 ilan)
    """
    all_jobs: list[Job] = []
    seen_urls: set[str] = set()

    with httpx.Client(follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            logger.info("Arbeitnow: fetching page %d/%d", page, max_pages)
            try:
                raw_jobs = _fetch_page(client, page)
            except Exception as exc:
                logger.error("Arbeitnow page %d failed: %s", page, exc)
                break

            if not raw_jobs:
                logger.info("Arbeitnow: no more jobs on page %d", page)
                break

            page_added = 0
            for raw in raw_jobs:
                job = _parse_job(raw)
                if job and job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)
                    page_added += 1

            logger.info("Arbeitnow page %d: %d relevant jobs", page, page_added)
            time.sleep(REQUEST_DELAY)

    logger.info("Arbeitnow: total %d relevant jobs fetched", len(all_jobs))
    return all_jobs
