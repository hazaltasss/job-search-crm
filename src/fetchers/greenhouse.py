"""
Greenhouse ATS API Fetcher.

Fetches student and internship listings directly from official Greenhouse ATS job boards
for top tech companies in Berlin & Germany (HelloFresh, SumUp, N26, GetYourGuide, Celonis,
Wolt, Solaris, Raisin, etc.).
API Endpoint:
    https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""
from __future__ import annotations
import logging
import re
import html
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# List of top tech companies with active Greenhouse boards in Berlin / Germany
GREENHOUSE_BOARDS: dict[str, str] = {
    "hellofresh": "HelloFresh",
    "sumup": "SumUp",
    "n26": "N26",
    "getyourguide": "GetYourGuide",
    "celonis": "Celonis",
    "wolt": "Wolt",
    "solarisbank": "Solaris",
    "raisin": "Raisin",
    "traderepublic": "Trade Republic",
    "datadog": "Datadog",
    "elastic": "Elastic",
    "stripe": "Stripe",
    "figma": "Figma",
    "canonical": "Canonical",
    "mongodb": "MongoDB",
    "cloudflare": "Cloudflare",
    "twilio": "Twilio",
    "pinterest": "Pinterest",
    "wise": "Wise",
    "adyen": "Adyen",
}

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

_STUDENT_REGEX = re.compile(
    r"\b(intern|internship|working student|werkstudent|praktikant|praktikum|thesis|studentische|student)\b",
    re.IGNORECASE,
)

_EXCLUDE_TITLE_REGEX = re.compile(
    r"\b(internal\s+(?:audit|control|sales|comms|communications|tooling))\b",
    re.IGNORECASE,
)

_BERLIN_REGEX = re.compile(r"\bberlin\b", re.IGNORECASE)
_GERMANY_REGEX = re.compile(r"\b(germany|deutschland|frankfurt|munich|münchen|hamburg|cologne|köln)\b", re.IGNORECASE)
_REMOTE_REGEX = re.compile(r"\bremote\b", re.IGNORECASE)
_NON_EU_REGEX = re.compile(
    r"\b(united states|usa|\bus\b|canada|austin|san francisco|new york|boston|chicago|india|brazil|mexico|australia|singapore|japan)\b",
    re.IGNORECASE,
)


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and unescape entities."""
    if not raw_html:
        return ""
    text = re.sub(r"<(?:p|div|br|li|h[1-6])[^>]*>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(text)
    return " ".join(clean.split()).strip()


def _is_student_role(title: str) -> bool:
    """Check if title corresponds to a student/intern position and not a false positive."""
    if _EXCLUDE_TITLE_REGEX.search(title) and not any(k in title.lower() for k in ["working student", "werkstudent", "intern", "praktik"]):
        return False
    return bool(_STUDENT_REGEX.search(title))


def _is_relevant_location(loc_str: str, offices: list[dict] | None = None) -> tuple[bool, bool, str]:
    """
    Check if location matches Berlin, Germany, or Germany-eligible Remote.
    Returns: (is_berlin, is_remote, cleaned_location_str)
    If irrelevant, returns (False, False, "")
    """
    office_names = " ".join(o.get("name", "") for o in (offices or []))
    combined = f"{loc_str} {office_names}".strip()

    # Reject explicitly non-EU/US locations unless Germany/Berlin is explicitly cited
    if _NON_EU_REGEX.search(combined) and not (_BERLIN_REGEX.search(combined) or _GERMANY_REGEX.search(combined)):
        return False, False, ""

    is_berlin = bool(_BERLIN_REGEX.search(combined))
    is_germany = bool(_GERMANY_REGEX.search(combined))
    is_remote = bool(_REMOTE_REGEX.search(combined))

    if is_berlin:
        clean_loc = "Berlin, Germany" if not is_remote else "Berlin, Germany (Remote)"
        return True, is_remote, clean_loc

    if is_germany:
        clean_loc = loc_str.strip() or "Germany"
        return False, is_remote, clean_loc

    if is_remote and any(r in combined.lower() for r in ["europe", "emea", "germany"]):
        return False, True, "Germany (Remote)"

    return False, False, ""


def parse_greenhouse_jobs(board_token: str, company_name: str, payload: dict) -> list[Job]:
    """Parse JSON payload from Greenhouse ATS API into Job objects."""
    jobs: list[Job] = []
    items = payload.get("jobs", [])

    for item in items:
        try:
            title = (item.get("title") or "").strip()
            if not title or not _is_student_role(title):
                continue

            loc_data = item.get("location", {})
            loc_name = loc_data.get("name", "") if isinstance(loc_data, dict) else str(loc_data)
            offices = item.get("offices", [])

            is_berlin, is_remote, clean_loc = _is_relevant_location(loc_name, offices)
            if not clean_loc:
                continue

            raw_content = item.get("content", "")
            desc = _clean_html(raw_content)

            url = (item.get("absolute_url") or "").strip()
            if not url:
                continue

            # Parse date
            updated_at = item.get("updated_at") or item.get("first_published") or ""
            posted_at = updated_at[:10] if len(updated_at) >= 10 else ""

            job_id = f"gh_{board_token}_{item.get('id')}"

            jobs.append(
                Job(
                    job_id=job_id,
                    source="greenhouse",
                    title=title,
                    company=company_name,
                    location=clean_loc,
                    url=url,
                    description=desc,
                    posted_at=posted_at,
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                    is_remote=is_remote,
                    is_berlin=is_berlin,
                )
            )
        except Exception as exc:
            logger.debug("Error parsing greenhouse job %s from %s: %s", item.get("id"), board_token, exc)
            continue

    return jobs


def fetch_board_jobs(client: httpx.Client, board_token: str, company_name: str) -> list[Job]:
    """Fetch jobs from a single Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        resp = client.get(url)
        if resp.status_code == 200:
            return parse_greenhouse_jobs(board_token, company_name, resp.json())
        logger.debug("Greenhouse board %s returned status %d", board_token, resp.status_code)
    except Exception as exc:
        logger.warning("Error fetching Greenhouse board %s: %s", board_token, exc)
    return []


def fetch_jobs() -> list[Job]:
    """Fetch matching jobs concurrently from all configured Greenhouse company boards."""
    logger.info("Fetching jobs from Greenhouse ATS boards (%d companies)...", len(GREENHOUSE_BOARDS))
    all_jobs: list[Job] = []

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(fetch_board_jobs, client, slug, name): name
                for slug, name in GREENHOUSE_BOARDS.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    jobs = future.result()
                    all_jobs.extend(jobs)
                    if jobs:
                        logger.info("Greenhouse board [%s]: %d matching student jobs", name, len(jobs))
                except Exception as exc:
                    logger.warning("Failed processing Greenhouse board [%s]: %s", name, exc)

    logger.info("Total student jobs fetched from Greenhouse boards: %d", len(all_jobs))
    return all_jobs
