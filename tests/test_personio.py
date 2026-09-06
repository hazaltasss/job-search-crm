"""
Unit tests for Personio ATS Fetcher.
"""
from __future__ import annotations
import pytest
from src.fetchers.personio import parse_personio_xml, _clean_html, _is_student_role, _is_relevant_location


def test_clean_html():
    raw = "<p>Join our <strong>Data Team</strong>.<br>Apply now!</p>"
    clean = _clean_html(raw)
    assert "Join our Data Team. Apply now!" in clean
    assert "<strong>" not in clean


def test_is_student_role():
    assert _is_student_role("Working Student - Data Engineering", "Working Student") is True
    assert _is_student_role("Internship - Product Analytics", "Intern") is True
    assert _is_student_role("Werkstudent Machine Learning", "part-time") is True
    assert _is_student_role("Praktikant AI Research", "internship") is True
    assert _is_student_role("Senior Backend Engineer", "full-time") is False
    assert _is_student_role("Internal Communications Specialist", "full-time") is False


def test_is_relevant_location():
    assert _is_relevant_location("Berlin", "") == (True, False, "Berlin, Germany")
    assert _is_relevant_location("Munich", "") == (False, False, "Munich, Germany")
    assert _is_relevant_location("Berlin", "home-office") == (True, True, "Berlin, Germany (Remote)")
    assert _is_relevant_location("Remote", "") == (False, True, "Germany (Remote)")
    assert _is_relevant_location("London", "") == (False, False, "")


def test_parse_personio_xml():
    mock_xml = """<?xml version="1.0" encoding="utf-8"?>
    <work-feed>
        <position>
            <id>101</id>
            <name>Working Student - Data Analytics (m/f/d)</name>
            <department>Data &amp; BI</department>
            <recruitingCategory>Working Student</recruitingCategory>
            <employmentType>part-time</employmentType>
            <schedule>part-time</schedule>
            <createdAt>2026-09-01T10:00:00+02:00</createdAt>
            <office>Berlin</office>
            <jobDescriptions>
                <jobDescription>
                    <name>Role</name>
                    <value><![CDATA[<p>Help us build data models and dashboards in Python and SQL.</p>]]></value>
                </jobDescription>
            </jobDescriptions>
        </position>
        <position>
            <id>102</id>
            <name>Lead Staff Engineer</name>
            <department>Engineering</department>
            <recruitingCategory>Direct</recruitingCategory>
            <employmentType>full-time</employmentType>
            <createdAt>2026-09-01T10:00:00+02:00</createdAt>
            <office>Berlin</office>
            <jobDescriptions>
                <jobDescription>
                    <name>Role</name>
                    <value><![CDATA[<p>Senior role</p>]]></value>
                </jobDescription>
            </jobDescriptions>
        </position>
    </work-feed>
    """

    jobs = parse_personio_xml("taxfix", "Taxfix", mock_xml)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.job_id == "personio_taxfix_101"
    assert j.company == "Taxfix"
    assert j.title == "Working Student - Data Analytics (m/f/d)"
    assert j.is_berlin is True
    assert j.source == "personio"
    assert "data models and dashboards" in j.description
    assert j.posted_at == "2026-09-01"
