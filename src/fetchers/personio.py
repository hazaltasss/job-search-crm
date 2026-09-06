"""
Personio ATS XML Fetcher.

Fetches student and internship listings directly from official Personio ATS feeds
for top tech companies and scale-ups in Berlin & Germany (Taxfix, Sennder, Tourlane,
Clue, Y42, Spryker, Deepset, Parloa, Taktile, etc.).
API Endpoint:
    https://{company_slug}.jobs.personio.de/xml
"""
from __future__ import annotations
import logging
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

PERSONIO_COMPANIES: dict[str, str] = {
    "taxfix": "Taxfix",
    "sennder": "Sennder",
    "tourlane": "Tourlane",
    "clue": "Clue",
    "y42": "Y42",
    "spryker": "Spryker",
    "deepset": "Deepset",
    "parloa": "Parloa",
    "taktile": "Taktile",
    "cozero": "Cozero",
    "urban-sports-club": "Urban Sports Club",
    "statista": "Statista",
    "channable": "Channable",
    "komoot": "Komoot",
    "flapd": "Flapd",
}

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/xml, text/xml, */*",
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
_GERMANY_CITIES_REGEX = re.compile(
    r"\b(germany|deutschland|frankfurt|munich|münchen|hamburg|cologne|köln|potsdam)\b",
    re.IGNORECASE,
)
_REMOTE_REGEX = re.compile(r"\b(remote|home-office|homeoffice|telework)\b", re.IGNORECASE)


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and unescape entities."""
    if not raw_html:
        return ""
    text = re.sub(r"<(?:p|div|br|li|h[1-6])[^>]*>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(text)
    return " ".join(clean.split()).strip()


def _is_student_role(title: str, recruiting_category: str = "") -> bool:
    """Check if title or category corresponds to a student/intern position."""
    if _EXCLUDE_TITLE_REGEX.search(title) and not any(
        k in title.lower() for k in ["working student", "werkstudent", "intern", "praktik"]
    ):
        return False
    combined = f"{title} {recruiting_category}".strip()
    return bool(_STUDENT_REGEX.search(combined))


def _is_relevant_location(office: str, schedule: str = "") -> tuple[bool, bool, str]:
    """
    Check if location matches Berlin, Germany, or Germany-eligible Remote.
    Returns: (is_berlin, is_remote, cleaned_location_str)
    """
    combined = f"{office} {schedule}".strip()
    is_berlin = bool(_BERLIN_REGEX.search(combined))
    is_remote = bool(_REMOTE_REGEX.search(combined))
    is_germany = bool(_GERMANY_CITIES_REGEX.search(combined))

    if is_berlin:
        clean_loc = "Berlin, Germany" if not is_remote else "Berlin, Germany (Remote)"
        return True, is_remote, clean_loc

    if is_remote:
        return False, True, "Germany (Remote)"

    if is_germany:
        clean_loc = f"{office.strip()}, Germany" if "germany" not in office.lower() else office.strip()
        return False, False, clean_loc

    return False, False, ""


def parse_personio_xml(slug: str, company_name: str, xml_content: str) -> list[Job]:
    """Parse Personio XML into Job objects."""
    jobs: list[Job] = []
    try:
        root = ET.fromstring(xml_content)
    except Exception as exc:
        logger.debug("Failed parsing Personio XML for %s: %s", slug, exc)
        return []

    for pos in root.findall(".//position"):
        try:
            pos_id = pos.findtext("id") or ""
            title = (pos.findtext("name") or "").strip()
            office = (pos.findtext("office") or "").strip()
            recruiting_cat = (pos.findtext("recruitingCategory") or "").strip()
            schedule = (pos.findtext("schedule") or "").strip()

            if not title or not _is_student_role(title, recruiting_cat):
                continue

            is_berlin, is_remote, clean_loc = _is_relevant_location(office, schedule)
            if not clean_loc:
                continue

            # Extract descriptions
            desc_parts = []
            for desc_node in pos.findall(".//jobDescription"):
                val = desc_node.findtext("value") or ""
                if val:
                    desc_parts.append(_clean_html(val))
            desc = " ".join(desc_parts).strip()

            url = f"https://{slug}.jobs.personio.de/job/{pos_id}"
            created_at = pos.findtext("createdAt") or ""
            posted_at = created_at[:10] if len(created_at) >= 10 else ""

            jobs.append(
                Job(
                    job_id=f"personio_{slug}_{pos_id}",
                    source="personio",
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
            logger.debug("Error parsing position item for %s: %s", slug, exc)
            continue

    return jobs


def fetch_company_jobs(client: httpx.Client, slug: str, company_name: str) -> list[Job]:
    """Fetch jobs from a single Personio company XML feed."""
    url = f"https://{slug}.jobs.personio.de/xml"
    try:
        resp = client.get(url)
        if resp.status_code == 200:
            return parse_personio_xml(slug, company_name, resp.text)
        logger.debug("Personio company %s returned status %d", slug, resp.status_code)
    except Exception as exc:
        logger.debug("Error fetching Personio company %s: %s", slug, exc)
    return []


def fetch_jobs() -> list[Job]:
    """Fetch student jobs concurrently from all configured Personio company feeds."""
    logger.info("Fetching jobs from Personio company feeds (%d companies)...", len(PERSONIO_COMPANIES))
    all_jobs: list[Job] = []

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(fetch_company_jobs, client, slug, name): name
                for slug, name in PERSONIO_COMPANIES.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    jobs = future.result()
                    all_jobs.extend(jobs)
                    if jobs:
                        logger.info("Personio company [%s]: %d matching student jobs", name, len(jobs))
                except Exception as exc:
                    logger.debug("Failed processing Personio [%s]: %s", name, exc)

    logger.info("Total student jobs fetched from Personio: %d", len(all_jobs))
    return all_jobs
