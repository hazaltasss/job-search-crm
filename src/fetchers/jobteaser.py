"""
JobTeaser Fetcher.

Fetches working student and internship listings from JobTeaser Europe & Germany.
Specifically targets university student roles in Berlin and Germany.
"""
from __future__ import annotations
import logging
import re
import html
import hashlib
import json
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

JOBTEASER_SEARCH_URLS = [
    "https://www.jobteaser.com/en/job-offers?contract=internship,student_job&location=Berlin%2C+Germany",
    "https://www.jobteaser.com/en/job-offers?contract=internship,student_job&job_field=data_analytics,software_it",
    "https://www.jobteaser.com/de/job-angebote?contract=internship,student_job&location=Berlin%2C+Deutschland",
]

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

_STUDENT_REGEX = re.compile(
    r"\b(intern|internship|working student|werkstudent|praktikant|praktikum|thesis|studentische|student)\b",
    re.IGNORECASE,
)

_BERLIN_REGEX = re.compile(r"\bberlin\b", re.IGNORECASE)
_REMOTE_REGEX = re.compile(r"\b(remote|home-office|homeoffice)\b", re.IGNORECASE)


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not raw_html:
        return ""
    text = re.sub(r"<(?:p|div|br|li|h[1-6])[^>]*>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(text)
    return " ".join(clean.split()).strip()


def _is_student_role(title: str) -> bool:
    return bool(_STUDENT_REGEX.search(title))


def _make_job_id(url: str) -> str:
    match = re.search(r"/(\d+)-", url)
    if match:
        return f"jt_{match.group(1)}"
    return "jt_" + hashlib.md5(url.encode()).hexdigest()[:12]


def parse_jobteaser_html(html_text: str) -> list[Job]:
    """Parse HTML content from JobTeaser into Job objects."""
    jobs: list[Job] = []
    seen_urls: set[str] = set()

    try:
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Check for schema.org JSON-LD first
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "JobPosting":
                        title = item.get("title", "").strip()
                        if not title or not _is_student_role(title):
                            continue
                        url = item.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        company = item.get("hiringOrganization", {}).get("name", "JobTeaser Partner")
                        loc_val = str(item.get("jobLocation", ""))
                        is_berlin = bool(_BERLIN_REGEX.search(loc_val))
                        is_remote = bool(_REMOTE_REGEX.search(loc_val))

                        jobs.append(
                            Job(
                                job_id=_make_job_id(url),
                                source="jobteaser",
                                title=title,
                                company=company,
                                location="Berlin, Germany" if is_berlin else "Germany",
                                url=url,
                                description=_clean_html(item.get("description", "")),
                                posted_at=(item.get("datePosted", "") or "")[:10],
                                fetched_at=datetime.now(timezone.utc).isoformat(),
                                is_remote=is_remote,
                                is_berlin=is_berlin,
                            )
                        )
            except Exception:
                pass

        if jobs:
            return jobs

        # 2. Fallback: Parse card elements in HTML
        cards = soup.find_all(lambda tag: tag.name in ["div", "article", "li"] and (
            tag.get("data-testid") == "job-card" or
            "job-card" in " ".join(tag.get("class", []))
        ))

        # If no explicit job-card containers, inspect links containing /job-offers/ or /job-angebote/
        if not cards:
            link_tags = soup.find_all("a", href=re.compile(r"/(?:job-offers|job-angebote)/"))
            for a in link_tags:
                href = a.get("href", "")
                full_url = href if href.startswith("http") else f"https://www.jobteaser.com{href}"
                if full_url in seen_urls:
                    continue
                title = a.get_text(strip=True)
                if not title or not _is_student_role(title):
                    continue

                seen_urls.add(full_url)
                parent_text = a.find_parent().get_text(" ", strip=True) if a.find_parent() else ""
                is_berlin = bool(_BERLIN_REGEX.search(f"{title} {parent_text}"))
                is_remote = bool(_REMOTE_REGEX.search(f"{title} {parent_text}"))

                jobs.append(
                    Job(
                        job_id=_make_job_id(full_url),
                        source="jobteaser",
                        title=title,
                        company="JobTeaser Employer",
                        location="Berlin, Germany" if is_berlin else "Germany",
                        url=full_url,
                        description=title,
                        posted_at="",
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                        is_remote=is_remote,
                        is_berlin=is_berlin,
                    )
                )
            return jobs

        for card in cards:
            title_elem = card.find(lambda t: t.name in ["a", "h2", "h3"] and ("/job-offers/" in t.get("href", "") or "/job-angebote/" in t.get("href", "") or "job-title" in " ".join(t.get("class", []))))
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or not _is_student_role(title):
                continue

            href = title_elem.get("href", "") or (title_elem.find("a").get("href", "") if title_elem.find("a") else "")
            full_url = href if href.startswith("http") else f"https://www.jobteaser.com{href}"
            if not href or full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            company_elem = card.find(class_=re.compile(r"company|enterprise", re.I))
            company = company_elem.get_text(strip=True) if company_elem else "JobTeaser Partner"

            loc_elem = card.find(class_=re.compile(r"location|city", re.I))
            loc_str = loc_elem.get_text(strip=True) if loc_elem else "Berlin, Germany"

            desc_elem = card.find(class_=re.compile(r"description|summary", re.I))
            desc = desc_elem.get_text(" ", strip=True) if desc_elem else title

            is_berlin = bool(_BERLIN_REGEX.search(f"{loc_str} {title}"))
            is_remote = bool(_REMOTE_REGEX.search(f"{loc_str} {title}"))

            jobs.append(
                Job(
                    job_id=_make_job_id(full_url),
                    source="jobteaser",
                    title=title,
                    company=company,
                    location="Berlin, Germany" if is_berlin else loc_str,
                    url=full_url,
                    description=desc,
                    posted_at="",
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                    is_remote=is_remote,
                    is_berlin=is_berlin,
                )
            )

    except Exception as exc:
        logger.debug("Failed parsing JobTeaser HTML: %s", exc)

    return jobs


def fetch_jobs() -> list[Job]:
    """Fetch student listings from JobTeaser."""
    logger.info("Fetching jobs from JobTeaser...")
    all_jobs: list[Job] = []

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
        for url in JOBTEASER_SEARCH_URLS:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    found = parse_jobteaser_html(resp.text)
                    all_jobs.extend(found)
                    logger.info("JobTeaser URL %s yielded %d listings", url, len(found))
                else:
                    logger.debug("JobTeaser %s returned status %d", url, resp.status_code)
            except Exception as exc:
                logger.debug("Error fetching JobTeaser %s: %s", url, exc)

    logger.info("Total student jobs fetched from JobTeaser: %d", len(all_jobs))
    return all_jobs
