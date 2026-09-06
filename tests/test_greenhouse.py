"""
Unit tests for Greenhouse ATS Fetcher.
"""
from __future__ import annotations
import pytest
from src.fetchers.greenhouse import parse_greenhouse_jobs, _clean_html, _is_relevant_location, _is_student_role


def test_clean_html():
    raw = "<p>Join our <strong>Data Analytics</strong> team in Berlin.<br/>Apply now!</p>"
    clean = _clean_html(raw)
    assert "Join our Data Analytics team in Berlin." in clean
    assert "<strong>" not in clean
    assert "<br/>" not in clean


def test_is_student_role():
    assert _is_student_role("Working Student - Data Analyst") is True
    assert _is_student_role("Marketing Intern (m/f/d)") is True
    assert _is_student_role("Werkstudent Software Engineering") is True
    assert _is_student_role("Praktikant AI Research") is True
    assert _is_student_role("Senior Data Scientist") is False
    assert _is_student_role("International Sales Manager") is False  # 'intern' substring in international shouldn't trigger


def test_is_relevant_location():
    # Berlin & Germany
    assert _is_relevant_location("Berlin, Germany", []) == (True, False, "Berlin, Germany")
    assert _is_relevant_location("Munich, Germany", []) == (False, False, "Munich, Germany")
    
    # Remote
    is_berlin, is_remote, loc = _is_relevant_location("Remote - Germany", [])
    assert is_remote is True
    assert "Germany" in loc
    
    # US / Non-European location should be rejected
    assert _is_relevant_location("New York, NY, United States", []) == (False, False, "")
    assert _is_relevant_location("San Francisco, CA", []) == (False, False, "")


def test_parse_greenhouse_jobs():
    mock_payload = {
        "jobs": [
            {
                "id": 8120152,
                "title": "Werkstudent - Data & AI Operations",
                "location": {"name": "Berlin, Germany"},
                "offices": [{"name": "Berlin HQ"}],
                "absolute_url": "https://careers.hellofresh.com/job/8120152",
                "content": "<p>We are looking for a working student in Berlin.</p>",
                "updated_at": "2026-09-01T10:00:00Z",
            },
            {
                "id": 9999999,
                "title": "Senior Staff Engineer",
                "location": {"name": "Berlin, Germany"},
                "offices": [],
                "absolute_url": "https://careers.hellofresh.com/job/9999999",
                "content": "<p>Senior position</p>",
                "updated_at": "2026-09-01T10:00:00Z",
            },
            {
                "id": 7777777,
                "title": "Product Intern",
                "location": {"name": "Austin, Texas, United States"},
                "offices": [],
                "absolute_url": "https://careers.hellofresh.com/job/7777777",
                "content": "<p>US only</p>",
                "updated_at": "2026-09-01T10:00:00Z",
            },
        ]
    }

    jobs = parse_greenhouse_jobs("hellofresh", "HelloFresh", mock_payload)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.job_id == "gh_hellofresh_8120152"
    assert job.company == "HelloFresh"
    assert job.title == "Werkstudent - Data & AI Operations"
    assert job.is_berlin is True
    assert job.source == "greenhouse"
    assert "working student in Berlin" in job.description
