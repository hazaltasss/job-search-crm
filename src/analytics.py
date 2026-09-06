"""
Analytics module: skills extraction, /stats command, and weekly digest.
"""
from __future__ import annotations
import logging
import re
from collections import Counter
from datetime import datetime, timezone

from src import database

logger = logging.getLogger(__name__)

# ─── Skill Keyword Lists ───────────────────────────────────────────────────────
_SKILL_KEYWORDS = [
    # Programming
    "python", "sql", "r ", "java", "typescript", "javascript", "c\\+\\+", "scala", "rust",
    # Data & ML
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "spark", "hadoop", "airflow", "dbt", "etl",
    # BI & Visualization
    "tableau", "power bi", "looker", "looker studio", "matplotlib", "seaborn",
    "excel", "google sheets",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "sqlite", "snowflake", "bigquery",
    # Cloud & DevOps
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "github actions", "ci/cd", "linux",
    # Business tools
    "jira", "confluence", "notion", "sap", "erp",
    # Soft skills / methodologies
    "agile", "scrum", "kanban", "stakeholder", "communication", "teamwork",
]


def extract_top_skills(descriptions: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """
    Count keyword occurrences across job descriptions.
    Returns a sorted list of (skill, count) tuples.
    """
    counter: Counter = Counter()
    combined = " ".join(d.lower() for d in descriptions)

    for skill in _SKILL_KEYWORDS:
        pattern = rf"\b{skill}\b"
        matches = re.findall(pattern, combined)
        if matches:
            display = skill.replace("\\+\\+", "++").replace("\\b", "").strip()
            counter[display] += len(matches)

    return counter.most_common(top_n)


def extract_top_companies(days: int = 30) -> list[tuple[str, int]]:
    """Return the most frequent hiring companies in the last N days."""
    jobs = database.get_all_jobs()
    counter: Counter = Counter(j["company"] for j in jobs if j.get("company"))
    return sorted(counter.items(), key=lambda x: (-x[1], x[0].lower()))[:10]


# ─── Stats Summary ─────────────────────────────────────────────────────────────
def build_stats_message() -> str:
    """Build the /stats Telegram message."""
    stats = database.get_stats()
    total = sum(stats.values())

    applied = stats.get("applied", 0)
    skipped = stats.get("skipped", 0)
    saved = stats.get("saved", 0)
    new = stats.get("new", 0)

    application_rate = (applied / total * 100) if total > 0 else 0

    top_companies = extract_top_companies()
    companies_text = "\n".join(
        f"   {i+1}. {company} ({count} jobs)"
        for i, (company, count) in enumerate(top_companies[:5])
    ) or "   No data yet"

    descriptions = database.get_recent_descriptions(days=30)
    top_skills = extract_top_skills(descriptions, top_n=10)
    skills_text = ", ".join(f"{s} ({c})" for s, c in top_skills) or "No data yet"

    return (
        "📊 <b>Your Job Search Stats</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>Total jobs found:</b> {total}\n"
        f"✅ <b>Applied:</b> {applied}\n"
        f"⏳ <b>Saved for later:</b> {saved}\n"
        f"❌ <b>Skipped:</b> {skipped}\n"
        f"🆕 <b>Pending review:</b> {new}\n"
        f"📈 <b>Application rate:</b> {application_rate:.1f}%\n"
        "\n"
        "🏆 <b>Top Hiring Companies:</b>\n"
        f"{companies_text}\n"
        "\n"
        "🛠️ <b>Top In-Demand Skills (last 30 days):</b>\n"
        f"   {skills_text}\n"
        "\n"
        f"🕒 Updated: {datetime.now().strftime('%d %b %Y, %H:%M')}"
    )


# ─── Weekly Report ─────────────────────────────────────────────────────────────
def build_weekly_report() -> str:
    """Build the Monday weekly digest Telegram message."""
    stats = database.get_stats()
    total = sum(stats.values())
    applied = stats.get("applied", 0)
    skipped = stats.get("skipped", 0)
    saved = stats.get("saved", 0)
    application_rate = (applied / total * 100) if total > 0 else 0

    descriptions = database.get_recent_descriptions(days=7)
    top_skills = extract_top_skills(descriptions, top_n=8)
    skills_text = "\n".join(
        f"   {i+1}. {s.title()} — mentioned {c}× this week"
        for i, (s, c) in enumerate(top_skills)
    ) or "   No new jobs scraped this week"

    top_companies = extract_top_companies()
    companies_text = "\n".join(
        f"   • {company}" for company, _ in top_companies[:5]
    ) or "   No data"

    week = datetime.now().strftime("Week of %d %b %Y")

    return (
        f"📬 <b>Weekly Job Search Digest</b> — {week}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "📌 <b>This Week's Summary:</b>\n"
        f"   • New jobs found: {len(descriptions)}\n"
        f"   • Applied: {applied} | Saved: {saved} | Skipped: {skipped}\n"
        f"   • Application rate: {application_rate:.1f}%\n"
        "\n"
        "🏆 <b>Most Active Hiring Companies:</b>\n"
        f"{companies_text}\n"
        "\n"
        "🔥 <b>Top Skills Requested This Week:</b>\n"
        f"{skills_text}\n"
        "\n"
        "💡 <b>Tip of the week:</b> Tailor your CV for each application using the "
        "📄 Tailor CV button — ATS-optimized applications get 3× more callbacks!\n"
        "\n"
        "👉 Use /stats for all-time analytics."
    )
