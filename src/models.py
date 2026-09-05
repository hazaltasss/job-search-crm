"""
Job data model shared across the entire application.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    """Represents a single job listing."""
    # Source metadata
    job_id: str          # Unique ID from the source platform
    source: str          # 'hiringcafe' | 'workingstudentjobs'

    # Core fields
    title: str
    company: str
    location: str
    url: str
    description: str = ""

    # Classification
    language: str = "en"       # 'en' | 'de' | 'bilingual' | 'unknown'
    is_remote: bool = False
    is_berlin: bool = False
    category: str = ""         # e.g. 'Data & AI', 'Software & IT', etc.
    match_score: int = 0       # Filter pipeline match score (0–100)

    # Dates
    posted_at: str = ""
    fetched_at: str = ""

    # CRM tracking
    status: str = "new"        # 'new' | 'applied' | 'interview' | 'rejected' | 'assessment' | 'skipped' | 'saved'
    applied_at: str = ""       # ISO date when status changed to 'applied'
    email_notes: str = ""      # Notes from Gmail sync (e.g. interview invitation details)
    sheet_row: Optional[int] = None
    db_id: Optional[int] = None

    def to_sheet_row(self) -> list:
        """Return a list of values for a Google Sheets row."""
        return [
            self.fetched_at,
            self.title,
            self.company,
            self.location,
            "Remote" if self.is_remote else "On-site",
            self.url,
            self.source,
            self.language.upper(),
            self.status.capitalize(),
            "",  # Notes column (empty by default)
        ]

    @property
    def short_location(self) -> str:
        loc = self.location.strip()
        if self.is_remote and "Berlin" not in loc:
            return f"{loc} (Remote)"
        return loc
