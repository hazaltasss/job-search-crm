"""
Unit tests for Workwise fetcher.
"""
from __future__ import annotations
import pytest
from src.fetchers.workwise import parse_job_page, _filter_candidate_urls, _clean_html


def test_clean_html():
    raw = "<div><span>Ab sofort</span> <br><span>Praktikum Data Analytics</span></div>"
    clean = _clean_html(raw)
    assert "Ab sofort Praktikum Data Analytics" in clean
    assert "<div>" not in clean
    assert "<br>" not in clean


def test_filter_candidate_urls():
    urls = [
        "https://www.workwise.io/job/568-werkstudent-als-entwickler-fuer-webapplikationen-m-w-d",
        "https://www.workwise.io/job/127784-junior-finance-manager-m-w-d",
        "https://www.workwise.io/job/45944-internship-as-founders-associate-in-a-start-up-m-f-d",
        "https://www.workwise.io/job/3897-praktikum-consulting-ma-projekte-m-w-d",
        "https://www.workwise.io/job/91356-medizinische-fachangestellte-fuer-kinderkardiologie-m-w-x",
    ]
    candidates = _filter_candidate_urls(urls)
    assert "https://www.workwise.io/job/568-werkstudent-als-entwickler-fuer-webapplikationen-m-w-d" in candidates
    assert "https://www.workwise.io/job/45944-internship-as-founders-associate-in-a-start-up-m-f-d" in candidates
    assert "https://www.workwise.io/job/3897-praktikum-consulting-ma-projekte-m-w-d" in candidates
    assert "https://www.workwise.io/job/91356-medizinische-fachangestellte-fuer-kinderkardiologie-m-w-x" not in candidates


def test_parse_job_page():
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Internship - AI & Data Analyst (m/f/d)",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Mercanis GmbH"
            },
            "jobLocation": [
                {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "Berlin",
                        "addressRegion": "BE",
                        "addressCountry": "DE"
                    }
                }
            ],
            "datePosted": "2026-09-01T10:00:00+02:00",
            "description": "<div>We are seeking an ambitious intern in Berlin for Python and SQL analytics.</div>"
        }
        </script>
    </head>
    <body></body>
    </html>
    """

    job = parse_job_page("https://www.workwise.io/job/12345-internship-ai-data-analyst", html_sample)
    assert job is not None
    assert job.job_id.startswith("ww_")
    assert job.source == "workwise"
    assert job.title == "Internship - AI & Data Analyst (m/f/d)"
    assert job.company == "Mercanis GmbH"
    assert "Berlin" in job.location
    assert job.is_berlin is True
    assert "Python and SQL analytics" in job.description
    assert job.posted_at == "2026-09-01"
