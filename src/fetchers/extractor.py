"""
Full Job Extractor: Fetches 100% of the job description and metadata from any URL.

Handles:
- LinkedIn Job Guest API & public pages
- Schema.org JSON-LD (JobPosting)
- Known ATS platforms (Greenhouse, Personio, Lever, Workable, Join.com, BerlinStartupJobs, etc.)
- Fallback semantic main-content extraction (strips headers, footers, navs, scripts)
"""
from __future__ import annotations
import html
import json
import logging
import re
import urllib.request
from typing import Optional
from bs4 import BeautifulSoup

from src.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

LOGIN_REJECT_TITLES = {
    "sign in", "login", "linkedin login", "log in",
    "security verification", "authwall", "welcome to linkedin",
    "anmelden", "einloggen"
}


def _get_html(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """Fetch URL with browser-like headers."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_soup_text(elem) -> str:
    """Convert an HTML element to clean, structured text preserving line breaks and bullets."""
    if not elem:
        return ""
    # Clone to avoid mutating original
    sub_soup = BeautifulSoup(str(elem), "html.parser")
    # Replace line break / paragraph tags with newlines
    for br in sub_soup.find_all(["br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
        br.insert_before("\n")
    for li in sub_soup.find_all("li"):
        li.insert_before("\n• ")
    text = sub_soup.get_text()
    # Normalize multiple newlines and spaces
    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines = []
    blank_count = 0
    for l in lines:
        if not l:
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
        else:
            blank_count = 0
            cleaned_lines.append(l)
    return "\n".join(cleaned_lines).strip()


def extract_full_job(url: str, raw_html: Optional[str] = None) -> dict[str, str]:
    """
    Extract complete 100% job description and metadata from a URL or raw HTML.
    Returns:
        {
            "title": str,
            "company": str,
            "location": str,
            "description": str,
        }
    """
    url_str = (url or "").strip()
    title = ""
    company = ""
    location = "Berlin, Germany"
    desc = ""

    # ── 1. Specialized LinkedIn Guest API ──────────────────────────────────────
    if "linkedin.com" in url_str.lower():
        li_id_match = re.search(r'(?:currentJobId=|/jobs/view/|/jobPosting/|/jobs/[^/]+-)([0-9]{8,12})', url_str)
        if li_id_match:
            li_job_id = li_id_match.group(1)
            # Rewrite search-results or tracking URL to canonical direct job view URL
            url_str = f"https://www.linkedin.com/jobs/view/{li_job_id}/"
            guest_api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{li_job_id}"
            try:
                api_html = _get_html(guest_api_url, timeout=12)
                soup_api = BeautifulSoup(api_html, "html.parser")
                t_tag = soup_api.find("h2", class_=re.compile(r"top-card-layout__title|topcard__title")) or soup_api.find("h1")
                if t_tag:
                    title = t_tag.get_text(strip=True)
                c_tag = (
                    soup_api.find("a", class_=re.compile(r"topcard__org-name-link|topcard__org-name|sub-nav-cta__optional-url"))
                    or soup_api.find("span", class_=re.compile(r"topcard__flavor"))
                )
                if c_tag:
                    company = c_tag.get_text(strip=True)
                d_tag = soup_api.find("div", class_=re.compile(r"show-more-less-html__markup|description__text"))
                if d_tag:
                    desc = _clean_soup_text(d_tag)
                l_tag = soup_api.find("span", class_=re.compile(r"topcard__flavor--bullet"))
                if l_tag:
                    location = l_tag.get_text(strip=True)
            except Exception as li_err:
                logger.warning("LinkedIn guest API extraction failed: %s", li_err)

    # ── 2. Generic Fetch & Parse if not fully satisfied ────────────────────────
    if not desc or len(desc) < 300:
        if not raw_html and url_str:
            try:
                raw_html = _get_html(url_str)
            except Exception as fetch_err:
                logger.warning("Failed to fetch %s: %s", url_str, fetch_err)

    if raw_html:
        soup = BeautifulSoup(raw_html, "html.parser")

        # A. Try schema.org JSON-LD (JobPosting)
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                content = (s.string or s.get_text() or "").strip()
                if not content:
                    continue
                ld_data = json.loads(content)
                items = ld_data if isinstance(ld_data, list) else [ld_data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    # Case-insensitive attribute lookup
                    ci = {k.lower(): v for k, v in item.items()}
                    type_str = str(ci.get("@type", "")).lower()
                    if "jobposting" in type_str:
                        cand_title = ci.get("title")
                        if not title and cand_title:
                            t = str(cand_title).strip()
                            if t.lower() not in LOGIN_REJECT_TITLES:
                                title = t

                        cand_org = ci.get("hiringorganization")
                        if not company and isinstance(cand_org, dict):
                            ci_org = {k.lower(): v for k, v in cand_org.items()}
                            company = str(ci_org.get("name", "")).strip()
                        elif not company and isinstance(cand_org, str):
                            company = cand_org.strip()

                        cand_desc = ci.get("description")
                        if cand_desc:
                            ld_desc_clean = _clean_soup_text(html.unescape(str(cand_desc)))
                            if len(ld_desc_clean) > len(desc):
                                desc = ld_desc_clean

                        loc_info = ci.get("joblocation")
                        if isinstance(loc_info, list) and loc_info:
                            loc_info = loc_info[0]
                        if isinstance(loc_info, dict):
                            ci_loc = {k.lower(): v for k, v in loc_info.items()}
                            addr = ci_loc.get("address")
                            if isinstance(addr, dict):
                                ci_addr = {k.lower(): v for k, v in addr.items()}
                                cand_loc = ci_addr.get("addresslocality") or ci_addr.get("addressregion") or ci_addr.get("addresscountry")
                                if isinstance(cand_loc, dict):
                                    cand_loc = cand_loc.get("name") or cand_loc.get("Name")
                                if cand_loc:
                                    location = str(cand_loc).strip()
            except Exception:
                pass

        # B. Check specialized CSS containers for known platforms
        if not desc or len(desc) < 400:
            containers = [
                # BerlinStartupJobs
                soup.find("div", class_=re.compile(r"bsj-template__content")),
                # Greenhouse / Lever / Workable / Personio
                soup.find("div", id=re.compile(r"job-details|job-description|content|posting-description")),
                soup.find("section", class_=re.compile(r"job-description|posting-requirements|show-more-less-html")),
                soup.find("div", class_=re.compile(r"show-more-less-html__markup|job-descriptions|job-details|description__text|vacancy-description")),
                soup.find("div", class_=re.compile(r"jobsearch-jobDescriptionText|posting-description")),
                # General article or main
                soup.find("article"),
                soup.find("main"),
            ]
            for cont in containers:
                if cont:
                    # Strip irrelevant tags inside container
                    for bad_tag in cont.find_all(["nav", "header", "footer", "script", "style", "aside", "form"]):
                        bad_tag.decompose()
                    candidate_text = _clean_soup_text(cont)
                    if len(candidate_text) > len(desc):
                        desc = candidate_text
                        break

        # C. Title extraction fallback
        if not title:
            h1 = soup.find("h1")
            if h1:
                cand_title = h1.get_text(strip=True)
                for sep in [" at ", " — ", " | ", " - "]:
                    if sep in cand_title:
                        cand_title = cand_title.split(sep)[0].strip()
                if cand_title.lower() not in LOGIN_REJECT_TITLES and not cand_title.lower().startswith("sign in"):
                    title = cand_title
            else:
                og_t = soup.find("meta", property="og:title")
                if og_t and og_t.get("content"):
                    title = og_t["content"].split(" at ")[0].split(" — ")[0].split(" | ")[0].strip()

        # D. Company extraction fallback
        if not company:
            og_t = soup.find("meta", property="og:title")
            if og_t and " at " in og_t.get("content", ""):
                company = og_t["content"].split(" at ")[1].split(" — ")[0].split(" | ")[0].strip()
            elif "personio" in url_str.lower():
                m = re.search(r"https?://([^.]+)\.jobs\.personio", url_str)
                if m:
                    company = m.group(1).capitalize()
            elif "csod.com" in url_str.lower():
                m = re.search(r"https?://([^.]+)\.csod\.com", url_str)
                if m:
                    company = m.group(1).capitalize()
            elif "join.com" in url_str.lower():
                m = re.search(r"join\.com/companies/([^/]+)", url_str)
                if m:
                    company = m.group(1).capitalize()

        # E. Clean title if company is appended with "//" or "-"
        if "//" in title:
            parts = title.split("//")
            title = parts[0].strip()
            if not company and len(parts) > 1:
                company = parts[1].strip()

    return {
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "description": desc.strip(),
    }
