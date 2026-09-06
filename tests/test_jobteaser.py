"""
Unit tests for JobTeaser fetcher.
"""
from __future__ import annotations
import pytest
from src.fetchers.jobteaser import parse_jobteaser_html, _clean_html, _is_student_role


def test_clean_html():
    raw = "<div><span>Studentische Hilfskraft</span> <strong>AI Lab</strong></div>"
    clean = _clean_html(raw)
    assert "Studentische Hilfskraft AI Lab" in clean


def test_is_student_role():
    assert _is_student_role("Working Student - Data Science") is True
    assert _is_student_role("Internship Business Analytics") is True
    assert _is_student_role("Werkstudent Python Developer") is True
    assert _is_student_role("Senior Cloud Architect") is False


def test_parse_jobteaser_html():
    mock_html = """
    <html>
    <body>
        <div data-testid="job-card" class="job-card">
            <a href="/en/job-offers/12345-working-student-data-analytics" class="job-title">
                Working Student - Data Analytics (m/f/d)
            </a>
            <span class="company-name">DeepTech Berlin GmbH</span>
            <span class="location">Berlin, Germany</span>
            <p class="description">Supporting our machine learning and analytics infrastructure.</p>
        </div>
        <div data-testid="job-card" class="job-card">
            <a href="/en/job-offers/99999-senior-devops-lead" class="job-title">
                Senior DevOps Lead
            </a>
            <span class="company-name">Legacy AG</span>
            <span class="location">Berlin, Germany</span>
        </div>
    </body>
    </html>
    """

    jobs = parse_jobteaser_html(mock_html)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.job_id.startswith("jt_")
    assert job.source == "jobteaser"
    assert job.title == "Working Student - Data Analytics (m/f/d)"
    assert job.company == "DeepTech Berlin GmbH"
    assert "Berlin" in job.location
    assert job.is_berlin is True
    assert "machine learning and analytics" in job.description
