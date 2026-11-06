"""
Filter pipeline: location, position type, language, and tech-category matching.

Pipeline evaluation order (job is skipped if any stage fails):
  1. Location     → Berlin (any mode) OR Germany-wide Remote
  2. PositionType → Working Student (Werkstudent) OR Intern (Praktikant) only
  3. Language     → Step 3a: HARD REJECT if German is mandatory
                    Step 3b: ACCEPT if English environment/requirement detected
                    Step 3c: Heuristic language ratio check
  4. Category     → Tech-focused roles (Data&AI, Software&IT, QA&Testing, IT Support, Tech Ops)
                    Minimum match score required (MIN_MATCH_SCORE = 30)
"""
from __future__ import annotations
import logging
import re
from typing import Sequence

from src.models import Job
from src.config import (
    BERLIN_KEYWORDS,
    REMOTE_KEYWORDS,
    LOCATION_REMOTE_KEYWORDS,
    FULL_REMOTE_PATTERNS,
    ONSITE_HYBRID_SIGNALS,
    NON_BERLIN_CITIES,
    NON_BERLIN_OFFICE_PATTERNS,
    ENGLISH_KEYWORDS,
    GERMAN_MANDATORY_PATTERNS,
    GERMAN_OPTIONAL_PATTERNS,
    WORKING_STUDENT_PATTERNS,
    INTERN_PATTERNS,
    CATEGORY_KEYWORDS,
    MIN_MATCH_SCORE,
)

logger = logging.getLogger(__name__)

# ─── Pre-compile all regex patterns once at import time ───────────────────────
_GERMAN_MANDATORY_RE = [
    re.compile(p, re.IGNORECASE) for p in GERMAN_MANDATORY_PATTERNS
]
_GERMAN_OPTIONAL_RE = re.compile(
    "|".join(GERMAN_OPTIONAL_PATTERNS), re.IGNORECASE
)
_WORKING_STUDENT_RE = [
    re.compile(p, re.IGNORECASE) for p in WORKING_STUDENT_PATTERNS
]
_INTERN_RE = [
    re.compile(p, re.IGNORECASE) for p in INTERN_PATTERNS
]
_FULL_REMOTE_RE = [
    re.compile(p, re.IGNORECASE) for p in FULL_REMOTE_PATTERNS
]
_ONSITE_HYBRID_RE = [
    re.compile(p, re.IGNORECASE) for p in ONSITE_HYBRID_SIGNALS
]
_NON_BERLIN_OFFICE_RE = re.compile(
    "|".join(NON_BERLIN_OFFICE_PATTERNS), re.IGNORECASE
)
_BERLIN_POSTCODE_RE = re.compile(r"\b1[0-4]\d{3}\b")

# German function words used for heuristic language detection
_GERMAN_FUNCTION_WORDS = frozenset({
    "und", "oder", "mit", "für", "auf", "bei", "sind", "wird", "wird",
    "einen", "eine", "einem", "des", "der", "die", "das", "den", "dem",
    "nicht", "auch", "aber", "als", "nach", "noch", "schon", "wenn",
    "wir", "sie", "ihr", "wer", "was", "wie", "von", "an", "in", "im",
    "ist", "sein", "haben", "werden", "können", "sollen", "müssen",
    "dein", "unser", "dich", "sich", "es", "ein",
})


def _text(*parts: str) -> str:
    """Combine and lowercase job text fields for keyword matching."""
    return " ".join(p.lower() for p in parts if p)


# ─── Filter Step 1: Location ─────────────────────────────────────────────────

def _check_location(job: Job) -> tuple[bool, bool, bool]:
    """
    Returns (passes, is_berlin, is_remote).

    Strict Location Rules:
      1. Berlin (onsite, hybrid, or remote in Berlin):
         PASSES only if it does NOT mandate office attendance/residency in another city (e.g. Munich, Hamburg, Frankfurt).
      2. Non-Berlin German City (e.g. Hamburg, Munich, Frankfurt, Stuttgart):
         REJECTS if it requires hybrid/onsite presence or fails explicit 100% full-remote verification.
      3. Germany-wide / General Remote (e.g. location="Remote, Germany"):
         PASSES if it explicitly declares remote and does NOT require physical attendance in a non-Berlin office.
    """
    loc_lower = (job.location or "").lower()
    title_lower = (job.title or "").lower()
    desc_lower = (job.description or "").lower()

    # 0. Check for explicit non-Berlin office or residency mandates in description
    has_non_berlin_office_mandate = bool(_NON_BERLIN_OFFICE_RE.search(desc_lower))
    requires_onsite_or_hybrid = any(p.search(desc_lower) for p in _ONSITE_HYBRID_RE)

    full_text = f"{loc_lower} {title_lower} {desc_lower}"
    is_strictly_full_remote = any(p.search(full_text) for p in _FULL_REMOTE_RE)

    # 1. Berlin check
    is_berlin = (
        any(kw in loc_lower for kw in BERLIN_KEYWORDS)
        or "berlin" in title_lower
        or bool(_BERLIN_POSTCODE_RE.search(loc_lower))
    )
    if is_berlin:
        # Cross-validation: If scraper tagged it as Berlin, but:
        # a) Neither title nor description mentions 'berlin', AND
        # b) Title, description, or URL mentions a non-Berlin German city (e.g. Stuttgart, Munich, Frankfurt), AND
        # c) The position is not confirmed 100% full remote:
        # -> REJECT: It is a false Berlin claim from a multi-city or mislabeled listing.
        berlin_in_text = "berlin" in title_lower or "berlin" in desc_lower
        has_other_city = any(
            re.search(r"\b" + re.escape(c) + r"\b", f"{title_lower} {desc_lower} {(job.url or '').lower()}")
            for c in NON_BERLIN_CITIES
        )
        if not berlin_in_text and has_other_city and not is_strictly_full_remote:
            logger.debug(
                "Rejected false Berlin tag: non-Berlin city found and Berlin absent in text: %s",
                job.title,
            )
            return False, False, False

        # If scraper tagged it as Berlin, but description demands an office in Munich/Hamburg/etc:
        if has_non_berlin_office_mandate and not is_strictly_full_remote:
            logger.debug("Rejected Berlin-tagged job with non-Berlin office mandate: %s", job.title)
            return False, False, False
        is_remote_mode = any(kw in loc_lower or kw in title_lower for kw in LOCATION_REMOTE_KEYWORDS) or is_strictly_full_remote
        return True, True, is_remote_mode

    # 2. Check if a specific non-Berlin physical city is named in location
    has_non_berlin_city = any(city in loc_lower for city in NON_BERLIN_CITIES)

    if has_non_berlin_city:
        # Hamburg, Munich, Stuttgart, etc.: ONLY pass if confirmed 100% full remote AND no office mandate
        if is_strictly_full_remote and not requires_onsite_or_hybrid and not has_non_berlin_office_mandate:
            return True, False, True
        # Otherwise: onsite/hybrid in another city -> strictly REJECT
        return False, False, False

    # 3. Non-specific city (e.g. location="Remote", "Deutschlandweit", "Germany")
    is_location_remote = any(kw in loc_lower for kw in LOCATION_REMOTE_KEYWORDS) or "remote" in title_lower
    if (is_location_remote or is_strictly_full_remote) and not requires_onsite_or_hybrid and not has_non_berlin_office_mandate:
        return True, False, True

    return False, False, False


# ─── Filter Step 2: Position Type ────────────────────────────────────────────

def _check_position_type(job: Job) -> tuple[bool, str]:
    """
    Returns (passes, detected_type).
    Only accepts Working Student (Werkstudent) or Intern (Praktikant/Internship).
    Checks both title AND description.
    """
    search_text = f"{job.title} {job.description or ''}"

    for pattern in _WORKING_STUDENT_RE:
        if pattern.search(search_text):
            return True, "Working Student"

    for pattern in _INTERN_RE:
        if pattern.search(search_text):
            return True, "Intern"

    return False, ""


# ─── Filter Step 3: Language ─────────────────────────────────────────────────

def _german_ratio(text: str) -> float:
    """Return the fraction of words that are German function words."""
    words = re.findall(r"\b[a-zäöüß]+\b", text.lower())
    if not words:
        return 0.0
    return sum(1 for w in words if w in _GERMAN_FUNCTION_WORDS) / len(words)


def _check_language(job: Job) -> tuple[bool, str]:
    """
    Three-stage strict language filter.

    Returns (passes, reason_string).

    Stage 3a — HARD REJECT:
        If the text contains any German-mandatory signal (Deutschkenntnisse,
        verhandlungssicher, fluent in German, C1/C2 German, etc.) → REJECT.

    Stage 3b — POSITIVE ACCEPT:
        If the text explicitly mentions English as working language / environment
        or contains strong English signals → ACCEPT.

    Stage 3c — HEURISTIC:
        If listing is from an English-language URL path (/en/) → ACCEPT.
        If German function word ratio < 12% (mostly English text) → ACCEPT.
        If German ratio ≥ 12% and no English signal → REJECT (German-only listing).
    """
    full_text = f"{job.title} {job.description or ''}"

    # ── 3a: Hard reject — German mandatory ────────────────────────────────────
    for pattern in _GERMAN_MANDATORY_RE:
        match = pattern.search(full_text)
        if match:
            # Check if this occurrence is negated by optional context (e.g. 'German is a plus', 'German university')
            start = max(0, match.start() - 25)
            end = min(len(full_text), match.end() + 45)
            context = full_text[start:end]
            if _GERMAN_OPTIONAL_RE.search(context):
                continue
            return False, f"German required: «{match.group(0)[:60]}»"

    full_text_lower = full_text.lower()

    # ── 3b: Positive — explicit English environment ────────────────────────────
    # Prioritize strong multi-word signals first, then single "english" keyword
    strong_signals = [kw for kw in ENGLISH_KEYWORDS if len(kw) > 8]
    for kw in strong_signals:
        if kw in full_text_lower:
            return True, f"English signal: «{kw}»"

    # ── 3c: Heuristic — detect listing language ───────────────────────────────
    if "/en/" in job.url:
        # English-path URL — still reject if German mandatory appeared above
        return True, "English URL path (/en/)"

    ratio = _german_ratio(full_text)

    if ratio < 0.12:
        # Predominantly non-German text → treat as English listing
        if "english" in full_text_lower:
            return True, f"English mentioned + low German ratio ({ratio:.0%})"
        # No English word at all but text is mostly not German either —
        # be conservative: accept only if very low German ratio
        if ratio < 0.05:
            return True, f"Very low German ratio ({ratio:.0%}) — likely English"
        # Ambiguous: German ratio 5–12%, no "english" — REJECT to be safe
        return False, f"Ambiguous language — German ratio {ratio:.0%}, no English signal"

    # German ratio ≥ 12%: German-dominant listing with no English signal → REJECT
    return False, f"German-dominant listing ({ratio:.0%} DE function words, no English signal)"


# ─── Filter Step 4: Tech Category Scoring ────────────────────────────────────

def _score_category(job: Job) -> tuple[str, int]:
    """
    Match the job against tech-only categories.
    Returns (best_category, score 0–100).

    To ensure only genuine tech/data/AI jobs pass:
    - If job TITLE contains tech keywords: strong signal, high score (50-100).
    - If job title does NOT contain tech keywords: description must have at least 3
      distinct tech keywords to avoid false positives (e.g. finance/editorial mentioning Excel).
    """
    search_text = _text(job.title, job.description or "")
    best_category = ""
    best_score = 0
    title_text = job.title.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        title_hits = sum(1 for kw in keywords if kw in title_text)
        desc_hits  = sum(1 for kw in keywords if kw in search_text)

        if title_hits >= 1:
            # Genuine tech title
            score = min(60 + (title_hits - 1) * 10 + desc_hits * 3, 100)
        elif desc_hits >= 3:
            # Tech-heavy description even if title is generic
            score = min(40 + (desc_hits - 3) * 5, 80)
        else:
            # Too weak / non-tech role with passing mention of a tool
            score = 0

        if score > best_score:
            best_score = score
            best_category = category

    return best_category, best_score


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def filter_jobs(jobs: Sequence[Job]) -> list[Job]:
    """
    Run the full 4-stage filter pipeline on raw Job objects.
    Returns only jobs that pass all filters AND meet MIN_MATCH_SCORE.
    """
    passed: list[Job] = []
    stats = {
        "total":    len(jobs),
        "location": 0,
        "position": 0,
        "language": 0,
        "score":    0,
    }

    for job in jobs:
        # ── Stage 1: Location ─────────────────────────────────────────────────
        loc_pass, is_berlin, is_remote = _check_location(job)
        if not loc_pass:
            stats["location"] += 1
            logger.debug("FILTERED [location] «%s» @ %s", job.title, job.location)
            continue

        job.is_berlin = is_berlin
        job.is_remote = is_remote

        # ── Stage 2: Position Type ────────────────────────────────────────────
        pos_pass, pos_type = _check_position_type(job)
        if not pos_pass:
            stats["position"] += 1
            logger.debug(
                "FILTERED [position_type] «%s» — not Werkstudent/Intern", job.title
            )
            continue

        # ── Stage 3: Language ─────────────────────────────────────────────────
        lang_pass, lang_reason = _check_language(job)
        if not lang_pass:
            stats["language"] += 1
            logger.debug(
                "FILTERED [language] «%s» — %s", job.title, lang_reason
            )
            continue
        else:
            logger.debug("PASSED  [language] «%s» — %s", job.title, lang_reason)

        # ── Stage 4: Tech Category Scoring ───────────────────────────────────
        category, score = _score_category(job)
        if score < MIN_MATCH_SCORE:
            stats["score"] += 1
            logger.debug(
                "FILTERED [score=%d] «%s» — no tech category match", score, job.title
            )
            continue

        job.category = category
        job.match_score = score
        passed.append(job)

    logger.info(
        "Filter pipeline: %d total → %d passed "
        "(filtered: %d location | %d position_type | %d language | %d score)",
        stats["total"],
        len(passed),
        stats["location"],
        stats["position"],
        stats["language"],
        stats["score"],
    )
    return passed
