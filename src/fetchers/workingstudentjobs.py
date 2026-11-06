"""
WorkingStudentJobs.de scraper.

Scrapes working student and internship postings in Berlin.
1. Parses job cards from listing pages (title, company, language chips, location, skills).
2. Filters for English-friendly tech jobs on the card level.
3. Fetches the full job description from the detail page (JSON-LD JobPosting) for matched cards.
"""
from __future__ import annotations
import os
import re
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

# Listing pages to scan — specifically targeting Berlin Tech & Student listings
_TARGET_PAGES = [
    f"{_BASE}/jobs/in/berlin?field=tech",
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


def _parse_detail_from_html(html: str) -> dict:
    """Extract description and locality from JSON-LD JobPosting inside page HTML."""
    res = {"description": "", "location": ""}
    try:
        soup = BeautifulSoup(html, "lxml")
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
                if data.get("@type") == "JobPosting":
                    desc = data.get("description", "")
                    if desc:
                        res["description"] = BeautifulSoup(desc, "lxml").get_text(separator="\n").strip()
                    loc_data = data.get("jobLocation")
                    if isinstance(loc_data, dict):
                        addr = loc_data.get("address", {})
                        if isinstance(addr, dict):
                            loc = addr.get("addressLocality")
                            if loc:
                                res["location"] = loc.strip()
                    elif isinstance(loc_data, list) and loc_data:
                        first = loc_data[0]
                        if isinstance(first, dict):
                            addr = first.get("address", {})
                            if isinstance(addr, dict):
                                loc = addr.get("addressLocality")
                                if loc:
                                    res["location"] = loc.strip()
                    if res["description"]:
                        return res
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Failed parsing detail from HTML: %s", exc)
    return res


def _fetch_full_description(client: httpx.Client, job_url: str) -> str:
    """Fetch detail page and extract description from JSON-LD JobPosting."""
    try:
        soup = _get_page(client, job_url)
        if not soup:
            return ""
        return _parse_detail_from_html(str(soup))["description"]
    except Exception as exc:
        logger.debug("Failed to fetch full description for %s: %s", job_url, exc)
    return ""


async def _fetch_details_batch(urls: list[str], max_concurrent: int = 8) -> dict[str, dict]:
    """Fetch multiple detail pages concurrently with semaphore, returning {url: {'description': ..., 'location': ...}}."""
    sem = asyncio.Semaphore(max_concurrent)
    results: dict[str, dict] = {}

    async def _fetch_one(client: httpx.AsyncClient, url: str) -> None:
        async with sem:
            try:
                resp = await client.get(url, headers=_HEADERS, timeout=10)
                if resp.status_code == 200:
                    results[url] = _parse_detail_from_html(resp.text)
                else:
                    results[url] = {"description": "", "location": ""}
            except Exception as exc:
                logger.debug("Failed async fetch for %s: %s", url, exc)
                results[url] = {"description": "", "location": ""}

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

        # Location from city button or chips
        city = ""
        btn = card.find("button", attrs={"aria-label": re.compile(r"popover for", re.I)})
        if btn:
            label = btn.get("aria-label", "")
            m = re.search(r"popover for\s+([A-Za-zäöüÄÖÜß\s\-\/\(\)]+)", label, re.I)
            if m:
                city = m.group(1).strip()
            if not city:
                span = btn.find("span")
                if span and span.get_text(strip=True):
                    city = span.get_text(strip=True)

        is_remote = "remote" in chips_text.lower()
        if not city:
            if "berlin" in chips_text.lower():
                city = "Berlin"
            elif is_remote:
                city = "Remote"

        if city:
            if is_remote and "berlin" not in city.lower():
                location = f"{city}, Remote"
            else:
                location = f"{city}, Germany"
        else:
            location = "Remote, Germany" if is_remote else "Germany"

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


def _fetch_with_playwright(max_pages: int = 2) -> list[Job]:
    """
    Scrapes WorkingStudentJobs.de using Playwright to seamlessly bypass Cloudflare Turnstile.
    """
    from playwright.sync_api import sync_playwright

    candidate_cards: list[dict] = []
    seen_urls: set[str] = set()
    now_iso = datetime.now(timezone.utc).isoformat()

    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--window-size=1280,800",
    ]
    if is_ci:
        launch_args.append("--no-sandbox")
    else:
        # Offscreen window satisfies Cloudflare Turnstile on macOS without popping up on screen
        launch_args.append("--window-position=-2400,-2400")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=is_ci,
            args=launch_args,
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for base_url in _TARGET_PAGES:
            sep = "&" if "?" in base_url else "?"
            for p_num in range(1, max_pages + 1):
                page_url = base_url if p_num == 1 else f"{base_url}{sep}page={p_num}"
                logger.info("WSJ (Playwright): scraping %s", page_url)
                try:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                    try:
                        page.wait_for_selector("article", timeout=10000)
                    except Exception:
                        pass
                    soup = BeautifulSoup(page.content(), "html.parser")
                    cards = soup.find_all("article")
                    if not cards:
                        break

                    for card in cards:
                        parsed = _parse_card(card, now_iso)
                        if not parsed or parsed["url"] in seen_urls:
                            continue
                        if parsed["is_german_only"]:
                            continue
                        seen_urls.add(parsed["url"])
                        candidate_cards.append(parsed)
                except Exception as exc:
                    logger.warning("WSJ page %s failed: %s", page_url, exc)
                    break

        logger.info("WSJ: %d candidate cards collected, fetching descriptions...", len(candidate_cards))

        all_jobs: list[Job] = []
        for parsed in candidate_cards:
            desc = ""
            loc_from_detail = ""
            try:
                page.goto(parsed["url"], wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(600)
                soup_d = BeautifulSoup(page.content(), "html.parser")
                for s in soup_d.find_all("script", type="application/ld+json"):
                    try:
                        d = json.loads(s.string or "{}")
                        if d.get("@type") == "JobPosting":
                            if d.get("description"):
                                desc = BeautifulSoup(d["description"], "html.parser").get_text("\n", strip=True)
                            loc_data = d.get("jobLocation")
                            if isinstance(loc_data, dict):
                                loc_from_detail = loc_data.get("address", {}).get("addressLocality", "")
                            elif isinstance(loc_data, list) and loc_data:
                                loc_from_detail = loc_data[0].get("address", {}).get("addressLocality", "")
                            if desc:
                                break
                    except Exception:
                        continue
                if not desc:
                    prose = soup_d.find("div", class_="prose") or soup_d.find("main")
                    if prose:
                        desc = prose.get_text("\n", strip=True)
            except Exception as e:
                logger.debug("Failed detail fetch for %s: %s", parsed["url"], e)

            if not desc:
                desc = f"{parsed['title']} at {parsed['company']}. Tags: {', '.join(parsed['chips'])}"

            final_location = parsed["location"]
            if loc_from_detail:
                final_location = f"{loc_from_detail.strip()}, Germany"

            is_berlin = "berlin" in final_location.lower()

            job = Job(
                job_id=_make_job_id(parsed["url"]),
                source="workingstudentjobs",
                title=parsed["title"],
                company=parsed["company"],
                location=final_location,
                url=parsed["url"],
                description=desc,
                language="en" if parsed["is_english"] else "unknown",
                is_remote=parsed["is_remote"],
                is_berlin=is_berlin,
                fetched_at=now_iso,
            )
            all_jobs.append(job)

        browser.close()
        return all_jobs


def _fetch_with_httpx(max_pages: int = 2) -> list[Job]:
    """
    Fallback HTTPX scraper for WorkingStudentJobs.de.
    """
    candidate_cards: list[dict] = []
    seen_urls: set[str] = set()
    now_iso = datetime.now(timezone.utc).isoformat()

    with httpx.Client(follow_redirects=True) as client:
        for base_url in _TARGET_PAGES:
            sep = "&" if "?" in base_url else "?"
            for page in range(1, max_pages + 1):
                page_url = base_url if page == 1 else f"{base_url}{sep}page={page}"
                logger.info("WSJ (httpx): scraping %s", page_url)

                soup = _get_page(client, page_url)
                if not soup:
                    break

                cards = soup.find_all("article")
                if not cards:
                    break

                from src.database import is_duplicate
                for card in cards:
                    parsed = _parse_card(card, now_iso)
                    if not parsed or parsed["url"] in seen_urls:
                        continue
                    if parsed["is_german_only"]:
                        continue
                    if is_duplicate(parsed["url"], title=parsed["title"], company=parsed["company"]):
                        continue

                    seen_urls.add(parsed["url"])
                    candidate_cards.append(parsed)

                time.sleep(REQUEST_DELAY)

    urls_to_fetch = [c["url"] for c in candidate_cards]
    details_map = asyncio.run(_fetch_details_batch(urls_to_fetch, max_concurrent=5))

    all_jobs: list[Job] = []
    for parsed in candidate_cards:
        detail = details_map.get(parsed["url"], {})
        full_desc = detail.get("description", "")
        if not full_desc:
            full_desc = f"{parsed['title']} at {parsed['company']}. Tags: {', '.join(parsed['chips'])}"

        final_location = parsed["location"]
        detail_loc = (detail.get("location") or "").strip()
        if detail_loc:
            final_location = f"{detail_loc}, Germany"

        is_berlin = "berlin" in final_location.lower()

        job = Job(
            job_id=_make_job_id(parsed["url"]),
            source="workingstudentjobs",
            title=parsed["title"],
            company=parsed["company"],
            location=final_location,
            url=parsed["url"],
            description=full_desc,
            language="en" if parsed["is_english"] else "unknown",
            is_remote=parsed["is_remote"],
            is_berlin=is_berlin,
            fetched_at=now_iso,
        )
        all_jobs.append(job)

    return all_jobs


def fetch_jobs(max_pages: int = 2) -> list[Job]:
    """
    Scrape WorkingStudentJobs.de for Berlin listings.
    Uses fast HTTPX directly; falls back to Playwright only if HTTPX returns 0 jobs.
    """
    try:
        jobs = _fetch_with_httpx(max_pages=max_pages)
        if jobs:
            logger.info("WorkingStudentJobs (httpx): %d relevant jobs fetched", len(jobs))
            return jobs
    except Exception as exc:
        logger.warning("WorkingStudentJobs httpx fetch error: %s. Attempting Playwright...", exc)

    try:
        jobs = _fetch_with_playwright(max_pages=max_pages)
        logger.info("WorkingStudentJobs (Playwright): %d relevant jobs fetched", len(jobs))
        return jobs
    except Exception as exc:
        logger.warning("WorkingStudentJobs Playwright fallback also failed: %s", exc)
        return []
