"""
Workwise.io Fetcher.

Discovers and fetches working student, internship, and junior tech roles from Workwise.io.
Uses Workwise category hubs and the real-time enquiry focus sitemap:
  - Category pages: /jobs/berlin, /jobs/berlin/it, /jobs/data-analyst, etc.
  - Sitemap: https://www.workwise.io/sitemaps/enquiryFocusPagesSitemap.xml
Extracts rich, verified schema.org/JobPosting JSON-LD metadata for each position.
"""
from __future__ import annotations
import logging
import re
import html
import hashlib
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from bs4 import BeautifulSoup

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

CATEGORY_URLS = [
    "https://www.workwise.io/jobs/berlin",
    "https://www.workwise.io/jobs/berlin/it",
    "https://www.workwise.io/jobs/berlin/startup",
    "https://www.workwise.io/jobs/berlin/business-development",
    "https://www.workwise.io/jobs/data-analyst",
    "https://www.workwise.io/jobs/data-scientist",
    "https://www.workwise.io/jobs/softwareentwickler",
    "https://www.workwise.io/jobs/python",
    "https://www.workwise.io/en/jobs/berlin",
]

SITEMAP_URL = "https://www.workwise.io/sitemaps/enquiryFocusPagesSitemap.xml"

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

_SLUG_PATTERN = re.compile(
    r"-(?:werkstudent|praktikant|praktikum|intern|internship|studentische|student|working-student|data-analyst|data-scientist|python|business-intelligence)-",
    re.IGNORECASE,
)

_STUDENT_TITLE_REGEX = re.compile(
    r"\b(intern|internship|working student|werkstudent|praktikant|praktikum|studentische|student|working-student)\b",
    re.IGNORECASE,
)

_BERLIN_REGEX = re.compile(r"\bberlin\b", re.IGNORECASE)
_REMOTE_REGEX = re.compile(r"\b(remote|home-office|homeoffice|telearbeit)\b", re.IGNORECASE)


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not raw_html:
        return ""
    text = re.sub(r"<(?:p|div|br|li|h[1-6])[^>]*>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(text)
    return " ".join(clean.split()).strip()


def _make_job_id(url: str) -> str:
    # If URL contains numeric ID like /job/45944-..., use that for stability
    match = re.search(r"/job/(\d+)-", url)
    if match:
        return f"ww_{match.group(1)}"
    return "ww_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _filter_candidate_urls(urls: list[str]) -> list[str]:
    """Filter list of Workwise URLs to only those matching target student/tech patterns."""
    candidates = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        # If it matches student slug pattern
        if _SLUG_PATTERN.search(u):
            seen.add(u)
            candidates.append(u)
    return candidates


def parse_job_page(url: str, html_text: str) -> Job | None:
    """Extract Job object from Workwise job posting HTML via JSON-LD schema."""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        job_data = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if data.get("@type") == "JobPosting":
                    job_data = data
                    break
            except Exception:
                continue

        if not job_data:
            return None

        title = (job_data.get("title") or "").strip()
        if not title:
            return None

        company_info = job_data.get("hiringOrganization") or {}
        company = (company_info.get("name") or "Workwise Partner").strip()

        # Location extraction
        loc_data = job_data.get("jobLocation")
        locality = ""
        country = "Germany"
        if isinstance(loc_data, list) and loc_data:
            addr = loc_data[0].get("address", {})
            locality = addr.get("addressLocality") or ""
            country = addr.get("addressCountry") or "Germany"
        elif isinstance(loc_data, dict):
            addr = loc_data.get("address", {})
            locality = addr.get("addressLocality") or ""
            country = addr.get("addressCountry") or "Germany"

        raw_desc = job_data.get("description") or ""
        desc = _clean_html(raw_desc)

        is_berlin = bool(_BERLIN_REGEX.search(locality)) or bool(_BERLIN_REGEX.search(desc[:300]))

        # Remote detection
        desc_header = desc[:400].lower()
        has_negative_remote = any(neg in desc_header for neg in ["kein homeoffice", "kein home-office", "keine remote", "ohne homeoffice"])
        is_telecommute = str(job_data.get("jobLocationType", "")).upper() == "TELECOMMUTE"
        positive_remote_keywords = [
            "100% remote", "fully remote", "remote möglich", "remote work",
            "homeoffice möglich", "home-office möglich", "mobiles arbeiten möglich",
            "deutschlandweit remote", "deutschlandweites homeoffice"
        ]
        has_positive_remote = any(p in desc_header for p in positive_remote_keywords)

        is_remote = (is_telecommute or has_positive_remote) and not has_negative_remote

        location = locality or "Germany"
        if is_berlin:
            location = "Berlin, Germany" if not is_remote else "Berlin, Germany (Remote)"
        elif is_remote:
            location = f"{location} (Remote)" if location != "Germany" else "Germany (Remote)"

        date_posted = job_data.get("datePosted") or ""
        posted_at = date_posted[:10] if len(date_posted) >= 10 else ""

        return Job(
            job_id=_make_job_id(url),
            source="workwise",
            title=title,
            company=company,
            location=location,
            url=url,
            description=desc,
            posted_at=posted_at,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            is_remote=is_remote,
            is_berlin=is_berlin,
        )
    except Exception as exc:
        logger.debug("Failed parsing Workwise job at %s: %s", url, exc)
        return None


def fetch_candidate_urls(client: httpx.Client) -> list[str]:
    """Gather unique candidate job URLs from category listing pages and sitemap."""
    candidate_urls: set[str] = set()

    # 1. Scrape category landing pages
    for cat_url in CATEGORY_URLS:
        try:
            resp = client.get(cat_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if "/job/" in href:
                        full_url = href if href.startswith("http") else f"https://www.workwise.io{href}"
                        candidate_urls.add(full_url)
        except Exception as exc:
            logger.debug("Failed scraping Workwise category %s: %s", cat_url, exc)

    # 2. Fetch enquiry focus sitemap for student positions
    try:
        sitemap_resp = client.get(SITEMAP_URL, timeout=REQUEST_TIMEOUT)
        if sitemap_resp.status_code == 200:
            all_locs = re.findall(r"<loc>(https://www.workwise.io/job/[^<]+)</loc>", sitemap_resp.text)
            matched_sitemap = _filter_candidate_urls(all_locs)
            candidate_urls.update(matched_sitemap)
            logger.info("Workwise sitemap yielded %d matching student links", len(matched_sitemap))
    except Exception as exc:
        logger.warning("Failed fetching Workwise sitemap %s: %s", SITEMAP_URL, exc)

    # Prefer student URLs or category jobs
    filtered_list = [u for u in candidate_urls if _SLUG_PATTERN.search(u) or any(c in u for c in ["berlin", "data", "python", "software"])]
    return list(set(filtered_list))[:60]  # Cap candidate fetches per run for speed


def fetch_jobs() -> list[Job]:
    """Fetch matching student jobs from Workwise."""
    logger.info("Fetching jobs from Workwise.io...")
    all_jobs: list[Job] = []

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
        candidates = fetch_candidate_urls(client)
        from src.database import is_duplicate
        candidates = [u for u in candidates if not is_duplicate(u)]
        logger.info("Workwise found %d new candidate URLs to inspect", len(candidates))
        if not candidates:
            return []

        def fetch_single(url: str) -> Job | None:
            try:
                r = client.get(url)
                if r.status_code == 200:
                    return parse_job_page(url, r.text)
            except Exception as exc:
                logger.debug("Workwise single fetch failed for %s: %s", url, exc)
            return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_single, url): url for url in candidates}
            for future in as_completed(futures):
                try:
                    job = future.result()
                    if job:
                        all_jobs.append(job)
                except Exception as exc:
                    logger.debug("Workwise pool error: %s", exc)

    logger.info("Total jobs parsed from Workwise: %d", len(all_jobs))
    return all_jobs
