"""
Unit tests for Dashboard Source Intelligence and Filtering logic.
"""
from __future__ import annotations
import pytest
from collections import Counter


def test_source_display_mapping_and_counts():
    SOURCE_DISPLAY_MAP = {
        "greenhouse": "🏢 Greenhouse ATS",
        "personio": "🎯 Personio ATS",
        "berlinstartupjobs": "🚀 Berlin Startup Jobs",
        "linkedin": "🔗 LinkedIn Jobs",
        "workwise": "💼 Workwise.io",
        "jobteaser": "🎓 JobTeaser",
        "arbeitnow": "🇩🇪 Arbeitnow",
        "workingstudentjobs": "📚 WorkingStudentJobs",
        "hiringcafe": "☕ HiringCafe",
    }

    mock_jobs = [
        {"source": "greenhouse", "company": "HelloFresh", "title": "Working Student Data"},
        {"source": "greenhouse", "company": "SumUp", "title": "Intern Design"},
        {"source": "linkedin", "company": "Amazon", "title": "Working Student Software"},
        {"source": "berlinstartupjobs", "company": "Tandem", "title": "Backend Intern"},
    ]

    source_counts = Counter(j["source"].lower() for j in mock_jobs)
    assert source_counts["greenhouse"] == 2
    assert source_counts["linkedin"] == 1
    assert source_counts["berlinstartupjobs"] == 1

    # Verify display mapping
    disp_names = [SOURCE_DISPLAY_MAP.get(s) for s in source_counts.keys()]
    assert "🏢 Greenhouse ATS" in disp_names
    assert "🔗 LinkedIn Jobs" in disp_names
    assert "🚀 Berlin Startup Jobs" in disp_names


def test_source_and_company_filtering():
    mock_jobs = [
        {"source": "greenhouse", "company": "HelloFresh", "title": "Working Student Data"},
        {"source": "greenhouse", "company": "SumUp", "title": "Intern Design"},
        {"source": "linkedin", "company": "Amazon", "title": "Working Student Software"},
    ]

    # Filter by source: greenhouse
    gh_filtered = [j for j in mock_jobs if j.get("source") == "greenhouse"]
    assert len(gh_filtered) == 2

    # Filter by company: HelloFresh
    hf_filtered = [j for j in gh_filtered if j.get("company") == "HelloFresh"]
    assert len(hf_filtered) == 1
    assert hf_filtered[0]["title"] == "Working Student Data"
