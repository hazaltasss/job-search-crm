"""
BerlinStartupJobs.com RSS Feed Fetcher.

Fetches tech internship and working student listings directly from Berlin Startup Jobs RSS feeds.
Feeds:
  - https://berlinstartupjobs.com/internships/feed/
  - https://berlinstartupjobs.com/feed/?s=working+student
  - https://berlinstartupjobs.com/feed/?s=werkstudent
"""
from __future__ import annotations
import logging
import re
import hashlib
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import httpx

from src.models import Job
from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_FEEDS = [
    "https://berlinstartupjobs.com/internships/feed/",
    "https://berlinstartupjobs.com/feed/?s=working+student",
    "https://berlinstartupjobs.com/feed/?s=werkstudent",
]

_POSITION_KEYWORDS = [
    "working student", "werkstudent", "intern", "internship",
    "praktikant", "praktikum", "studentische", "student assistant",
    "student",
]

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _make_job_id(url: str) -> str:
    return "bsj_" + hashlib.md5(url.encode()).hexdigest()[:12]


import html


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and unescape entities."""
    # Replace block tags with a space so words don't merge
    text = re.sub(r"<(?:p|div|br|li|h[1-6])[^>]*>", " ", raw_html, flags=re.IGNORECASE)
    # Strip remaining inline tags without extra spaces
    text = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(text)
    return " ".join(clean.split()).strip()


def _parse_pub_date(pub_date_str: str) -> str:
    """Parse RSS pubDate to YYYY-MM-DD."""
    if not pub_date_str:
        return ""
    try:
        # e.g., 'Wed, 02 Sep 2026 16:09:00 +0000'
        dt = datetime.strptime(pub_date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_feed_xml(xml_content: str, is_internship_feed: bool = False) -> list[Job]:
    """Parse RSS XML content into a list of Job dataclass objects."""
    jobs: list[Job] = []
    try:
        root = ET.fromstring(xml_content)
    except Exception as exc:
        logger.warning("Failed to parse Berlin Startup Jobs XML: %s", exc)
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    for item in channel.findall("item"):
        try:
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            pub_elem = item.find("pubDate")

            raw_title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
            raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
            pub_date = _parse_pub_date(pub_elem.text if pub_elem is not None and pub_elem.text else "")

            if not url or not raw_title:
                continue

            categories = [
                cat.text.strip() for cat in item.findall("category")
                if cat.text
            ]

            # Split title and company: e.g. "Backend Developer // Tandem"
            if " // " in raw_title:
                title, company = raw_title.split(" // ", 1)
            elif " - " in raw_title:
                title, company = raw_title.split(" - ", 1)
            else:
                title = raw_title
                company = "Berlin Startup"

            title = title.strip()
            company = company.strip()
            desc = _clean_html(raw_desc)

            # Check relevance
            combined_text = f"{title.lower()} {' '.join(c.lower() for c in categories)} {desc[:300].lower()}"
            if not is_internship_feed and not any(kw in combined_text for kw in _POSITION_KEYWORDS):
                continue

            is_remote = "remote" in title.lower() or "remote" in desc.lower() or any("remote" in c.lower() for c in categories)
            location = "Berlin, Germany (Remote)" if is_remote else "Berlin, Germany"

            jobs.append(
                Job(
                    job_id=_make_job_id(url),
                    source="berlinstartupjobs",
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description=desc,
                    posted_at=pub_date,
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                    is_remote=is_remote,
                    is_berlin=True,
                )
            )
        except Exception as item_err:
            logger.debug("Error parsing item from Berlin Startup Jobs: %s", item_err)
            continue

    return jobs


def fetch_jobs() -> list[Job]:
    """Fetch jobs from all configured Berlin Startup Jobs RSS feeds."""
    logger.info("Fetching jobs from Berlin Startup Jobs RSS feeds...")
    all_jobs: list[Job] = []
    seen_urls: set[str] = set()

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
        for feed_url in _FEEDS:
            try:
                resp = client.get(feed_url)
                if resp.status_code == 200:
                    is_intern_feed = "internships" in feed_url
                    feed_jobs = parse_feed_xml(resp.text, is_internship_feed=is_intern_feed)
                    for j in feed_jobs:
                        if j.url not in seen_urls:
                            seen_urls.add(j.url)
                            all_jobs.append(j)
                    logger.info("Berlin Startup Jobs feed %s yielded %d listings", feed_url, len(feed_jobs))
                else:
                    logger.warning("Berlin Startup Jobs feed %s returned status %d", feed_url, resp.status_code)
            except Exception as exc:
                logger.warning("Failed fetching Berlin Startup Jobs feed %s: %s", feed_url, exc)

    logger.info("Total unique jobs fetched from Berlin Startup Jobs: %d", len(all_jobs))
    return all_jobs
