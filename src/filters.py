"""
Filter pipeline: location, position type, language, and tech-category matching.

Pipeline sırası (her biri başarısız olursa job atlanır):
  1. Location   → Berlin (her mod) VEYA Germany-wide Remote
  2. PositionType → Sadece Working Student / Werkstudent VEYA Intern / Praktikant
  3. Language   → Adım 3a: Almanca zorunluluğu varsa HARD REJECT
                  Adım 3b: İngilizce ortam/şartı varsa ACCEPT
                  Adım 3c: Heuristik → listing metninin dil tespiti
  4. Category   → Sadece teknoloji/yazılım odaklı (Data&AI, Software&IT, Business Tech)
                  Minimum 30 puan skor gerekli
"""
from __future__ import annotations
import logging
import re
from typing import Sequence

from src.models import Job
from src.config import (
    BERLIN_KEYWORDS,
    REMOTE_KEYWORDS,
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
    Passes if:
      - Location mentions Berlin (any work mode), OR
      - Position is fully remote / Germany-wide
    """
    loc_lower = job.location.lower()
    desc_lower = (job.description or "").lower()
    title_lower = job.title.lower()
    combined = f"{loc_lower} {title_lower} {desc_lower}"

    is_remote = any(kw in combined for kw in REMOTE_KEYWORDS)
    is_berlin = any(kw in loc_lower for kw in BERLIN_KEYWORDS)

    return (is_berlin or is_remote), is_berlin, is_remote


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
