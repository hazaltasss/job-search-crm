import pytest
from src.fetchers.berlinstartupjobs import parse_feed_xml, _clean_html, _parse_pub_date

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Berlin Startup Jobs</title>
    <item>
        <title>Working Student Data Analytics // Zalando</title>
        <link>https://berlinstartupjobs.com/internships/working-student-data-analytics-zalando/</link>
        <pubDate>Wed, 02 Sep 2026 16:09:00 +0000</pubDate>
        <category><![CDATA[Data Analytics]]></category>
        <category><![CDATA[Internships]]></category>
        <description><![CDATA[<p>Looking for a motivated <strong>Working Student</strong> to assist our Data Science team in Berlin.</p>]]></description>
    </item>
    <item>
        <title>Senior VP Sales // Enterprise AG</title>
        <link>https://berlinstartupjobs.com/sales/senior-vp-sales/</link>
        <pubDate>Thu, 03 Sep 2026 10:00:00 +0000</pubDate>
        <category><![CDATA[Sales]]></category>
        <description><![CDATA[<p>Looking for 15+ years experience.</p>]]></description>
    </item>
</channel>
</rss>
"""

def test_parse_feed_xml():
    jobs = parse_feed_xml(SAMPLE_RSS_XML, is_internship_feed=False)
    # The Senior VP Sales should be filtered out by position keywords
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Working Student Data Analytics"
    assert job.company == "Zalando"
    assert "https://berlinstartupjobs.com/internships/" in job.url
    assert job.source == "berlinstartupjobs"
    assert job.posted_at == "2026-09-02"
    assert "Data Science" in job.description
    assert job.is_berlin is True

def test_clean_html():
    raw = "<p>Hello <strong>World</strong>! &#038; Welcome &amp; Enjoy</p>"
    clean = _clean_html(raw)
    assert clean == "Hello World! & Welcome & Enjoy"

def test_parse_pub_date():
    parsed = _parse_pub_date("Wed, 02 Sep 2026 16:09:00 +0000")
    assert parsed == "2026-09-02"
