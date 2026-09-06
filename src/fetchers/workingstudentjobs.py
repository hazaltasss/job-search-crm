"""
WorkingStudentJobs.de scraper.

Scrapes working student and internship postings in Berlin.
1. Parses job cards from listing pages (title, company, language chips, location, skills).
2. Filters for English-friendly tech jobs on the card level.
3. Fetches the full job description from the detail page (JSON-LD JobPosting) for matched cards.
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
import hashlib
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

_BASE = "https://www.workingstudentjobs.de"

# Listing pages to scan — specifically targeting Tech & Engineering
_TARGET_PAGES = [
    f"{_BASE}/jobs/in/berlin?field=tech",
    f"{_BASE}/?field=tech",
    f"{_BASE}/jobs/in/berlin",
]

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _make_job_id(url: str) -> str:
    return "wsj_" + hashlib.md5(url.encode()).hexdigest()[:12]


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=6),
    reraise=False,
)
def _get_page(client: httpx.Client, url: str) -> BeautifulSoup | None:
    resp = client.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return None
    return BeautifulSoup(resp.text, "lxml")


def _parse_description_from_html(html: str) -> str:
    """Extract description from JSON-LD JobPosting inside page HTML."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
                if data.get("@type") == "JobPosting":
                    desc = data.get("description", "")
                    if desc:
                        return BeautifulSoup(desc, "lxml").get_text(separator="\n").strip()
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Failed parsing description from HTML: %s", exc)
    return ""


def _fetch_full_description(client: httpx.Client, job_url: str) -> str:
    """Fetch detail page and extract description from JSON-LD JobPosting."""
    try:
        soup = _get_page(client, job_url)
        if not soup:
            return ""
        return _parse_description_from_html(str(soup))
    except Exception as exc:
        logger.debug("Failed to fetch full description for %s: %s", job_url, exc)
    return ""


async def _fetch_descriptions_batch(urls: list[str], max_concurrent: int = 5) -> dict[str, str]:
    """Fetch multiple detail pages concurrently with semaphore, returning {url: description}."""
    sem = asyncio.Semaphore(max_concurrent)
    results: dict[str, str] = {}

    async def _fetch_one(client: httpx.AsyncClient, url: str) -> None:
        async with sem:
            try:
                resp = await client.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    results[url] = _parse_description_from_html(resp.text)
                else:
                    results[url] = ""
            except Exception as exc:
                logger.debug("Failed async fetch for %s: %s", url, exc)
                results[url] = ""
            await asyncio.sleep(0.1)  # Minimal politeness delay

    if not urls:
        return results

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [_fetch_one(client, url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results


def _parse_card(card, now_iso: str) -> dict | None:
    """Extract card attributes from the listing card element."""
    try:
        title_tag = card.find("h3")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)
        link_tag = title_tag.find("a", href=True)
        if not link_tag:
            return None

        href = link_tag["href"]
        url = href if href.startswith("http") else f"{_BASE}{href}"

        # Company
        co_tag = card.find("a", href=lambda h: h and "/jobs/at/" in h)
        if co_tag:
            company = co_tag.get_text(strip=True)
        else:
            img = card.find("img", alt=True)
            company = img["alt"].replace(" logo", "").strip() if img else "Unknown"

        # Check for aggregator profiles or "Company: Role" title structures
        aggregator_names = {"venture capital careers", "recruiting", "career", "jobs", "aggregator", "unknown"}
        if ": " in title:
            prefix, rest = title.split(": ", 1)
            prefix = prefix.strip()
            # If prefix looks like a company name and not a generic role descriptor
            if 2 <= len(prefix) <= 40 and not any(kw in prefix.lower() for kw in ["working student", "werkstudent", "intern", "praktik", "thesis"]):
                if company.lower() in aggregator_names or prefix.lower() in company.lower() or company.lower() in prefix.lower():
                    company = prefix
                    title = rest.strip()

        # Chips: language, role type, location, remote, skills
        chips = [
            c.get_text(strip=True)
            for c in card.find_all("span", class_=lambda c: c and "chip__label" in c)
        ]
        chips_text = " ".join(chips)

        # Location
        location = "Berlin"
        is_remote = "remote" in chips_text.lower()
        if is_remote and "berlin" not in chips_text.lower():
            location = "Remote, Germany"
        elif "berlin" in chips_text.lower():
            location = "Berlin, Germany"

        # Language from chips
        # If chip is explicitly German only, mark language as German
        is_english = any("english" in c.lower() for c in chips)
        is_german_only = ("german" in chips_text.lower()) and not is_english

        return {
            "title": title,
            "company": company,
            "url": url,
            "location": location,
            "is_remote": is_remote,
            "chips": chips,
            "is_english": is_english,
            "is_german_only": is_german_only,
        }
    except Exception as exc:
        logger.debug("Card parse error: %s", exc)
        return None


def fetch_jobs(max_pages: int = 3) -> list[Job]:
    """
    Scrape WorkingStudentJobs.de for Berlin listings.
    Phase 1: Collects job cards synchronously.
    Phase 2: Concurrently fetches job descriptions via asyncio batching.
    """
    candidate_cards: list[dict] = []
    seen_urls: set[str] = set()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Phase 1: Scan listing pages
    with httpx.Client(follow_redirects=True) as client:
        for base_url in _TARGET_PAGES:
            sep = "&" if "?" in base_url else "?"
            for page in range(1, max_pages + 1):
                page_url = base_url if page == 1 else f"{base_url}{sep}page={page}"
                logger.info("WSJ: scraping %s", page_url)

                soup = _get_page(client, page_url)
                if not soup:
                    break

                cards = soup.find_all("article")
                if not cards:
                    break

                for card in cards:
                    parsed = _parse_card(card, now_iso)
                    if not parsed or parsed["url"] in seen_urls:
                        continue

                    # If the card explicitly states "German" only, skip
                    if parsed["is_german_only"]:
                        continue

                    seen_urls.add(parsed["url"])
                    candidate_cards.append(parsed)

                time.sleep(REQUEST_DELAY)

    # Phase 2: Fetch full descriptions concurrently with asyncio
    urls_to_fetch = [c["url"] for c in candidate_cards]
    logger.info("WSJ: Concurrently fetching descriptions for %d jobs...", len(urls_to_fetch))
    descriptions_map = asyncio.run(_fetch_descriptions_batch(urls_to_fetch, max_concurrent=5))

    all_jobs: list[Job] = []
    for parsed in candidate_cards:
        full_desc = descriptions_map.get(parsed["url"], "")
        if not full_desc:
            full_desc = f"{parsed['title']} at {parsed['company']}. Tags: {', '.join(parsed['chips'])}"

        job = Job(
            job_id=_make_job_id(parsed["url"]),
            source="workingstudentjobs",
            title=parsed["title"],
            company=parsed["company"],
            location=parsed["location"],
            url=parsed["url"],
            description=full_desc,
            language="en" if parsed["is_english"] else "unknown",
            is_remote=parsed["is_remote"],
            is_berlin=True,
            fetched_at=now_iso,
        )
        all_jobs.append(job)

    logger.info("WorkingStudentJobs: %d relevant jobs fetched", len(all_jobs))
    return all_jobs
