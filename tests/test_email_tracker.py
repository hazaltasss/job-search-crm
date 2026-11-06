"""
Unit tests for email_tracker.py date querying and metric calculation.
"""
from datetime import date, datetime, timezone, timedelta
import pytest

from src.email_tracker import (
    build_imap_search_query,
    calculate_email_metrics,
    generate_career_insights,
)


def test_build_imap_search_query_with_days_back():
    query = build_imap_search_query(days_back=14)
    expected_since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%d-%b-%Y")
    assert query == f'(SINCE "{expected_since}")'


def test_build_imap_search_query_with_start_and_end_date():
    start = date(2026, 1, 1)
    end = date(2026, 2, 1)
    query = build_imap_search_query(start_date=start, end_date=end)
    assert query == '(SINCE "01-Jan-2026" BEFORE "01-Feb-2026")'


def test_build_imap_search_query_with_only_start_date():
    start = date(2026, 3, 15)
    query = build_imap_search_query(start_date=start)
    assert query == '(SINCE "15-Mar-2026")'


def test_build_imap_search_query_with_only_end_date():
    end = date(2026, 4, 20)
    query = build_imap_search_query(end_date=end)
    assert query == '(BEFORE "20-Apr-2026")'


def test_build_imap_search_query_all():
    query = build_imap_search_query()
    assert query == "ALL"


def test_calculate_email_metrics():
    sample_updates = [
        {
            "category": "RECEIVED",
            "company": "Zalando",
            "position": "Data Analyst Intern",
            "date": "01 Jan 2026",
        },
        {
            "category": "INTERVIEW",
            "company": "Zalando",
            "position": "Data Analyst Intern",
            "date": "05 Jan 2026",
        },
        {
            "category": "ASSESSMENT",
            "company": "Delivery Hero",
            "position": "Python Engineer",
            "date": "02 Jan 2026",
        },
        {
            "category": "REJECTED",
            "company": "N26",
            "position": "BI Working Student",
            "date": "03 Jan 2026",
        },
        {
            "category": "RECEIVED",
            "company": "SoundCloud",
            "position": "ML Intern",
            "date": "04 Jan 2026",
        },
    ]

    metrics = calculate_email_metrics(sample_updates)

    assert metrics["total_emails"] == 5
    assert metrics["unique_companies_count"] == 4
    assert set(metrics["unique_companies"]) == {"Zalando", "Delivery Hero", "N26", "SoundCloud"}
    assert metrics["categories"]["INTERVIEW"] == 1
    assert metrics["categories"]["ASSESSMENT"] == 1
    assert metrics["categories"]["REJECTED"] == 1
    assert metrics["categories"]["RECEIVED"] == 2
    # Responded companies: Zalando (Interview), Delivery Hero (Assessment), N26 (Rejected) = 3 out of 4 unique companies
    assert metrics["responded_companies_count"] == 3
    assert metrics["response_rate_percent"] == 75.0
    assert metrics["interview_rate_percent"] == 25.0


def test_calculate_email_metrics_empty():
    metrics = calculate_email_metrics([])
    assert metrics["total_emails"] == 0
    assert metrics["unique_companies_count"] == 0
    assert metrics["response_rate_percent"] == 0.0


def test_generate_career_insights_fallback():
    sample_metrics = {
        "total_emails": 10,
        "unique_companies_count": 8,
        "categories": {
            "INTERVIEW": 2,
            "ASSESSMENT": 1,
            "REJECTED": 3,
            "RECEIVED": 4,
        },
        "response_rate_percent": 75.0,
        "interview_rate_percent": 25.0,
        "unique_companies": ["A", "B"],
    }
    insights = generate_career_insights(sample_metrics, [], use_ai=False)
    assert "Başvuru Karnesi" in insights or "Analiz" in insights
    assert "Mülakat" in insights
