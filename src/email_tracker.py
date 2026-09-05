"""
email_tracker.py — Gmail Integration & AI Email Classifier for Job Applications.

1. Connects to Gmail via IMAP (SSL) using an App Password.
2. Scans recent emails related to job applications and interviews.
3. Uses Gemini 1.5 Flash to accurately classify the email:
   - INTERVIEW: Interview invitation, screening call, or scheduling request
   - REJECTED: Application unsuccessful notification
   - ASSESSMENT: Online coding test, Hackerrank, or assessment link
   - RECEIVED: Application received confirmation
   - UNRELATED: Non-application emails
4. Automatically updates job statuses and notes in SQLite (jobs.db).
"""
from __future__ import annotations
import email
from email.header import decode_header
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import google.generativeai as genai

from src.config import GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY
from src.database import get_applied_jobs, update_job_from_email, find_job_by_company

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """
You are an intelligent email analyzer assisting Hazal Taş with tracking her job applications in Berlin, Germany.

Analyze the following email and determine if it is related to an active job application:

From: {sender}
Subject: {subject}
Date: {date}
Body snippet:
{body}

Classify this email into ONE of the following categories:
- "INTERVIEW": Invitation to an interview, phone screen, technical chat, or link to schedule an interview.
- "REJECTED": Notification that the candidate was not selected or the position was filled.
- "ASSESSMENT": Invitation to complete an online coding challenge (e.g. HackerRank, Codility, LeetCode) or questionnaire.
- "RECEIVED": Automated confirmation that the application was received and is under review.
- "UNRELATED": Marketing, newsletter, spam, or not related to Hazal's job applications.

Return ONLY a valid JSON object with the following structure (no markdown formatting, no code fences):
{{
  "is_job_related": true,
  "category": "INTERVIEW",
  "company": "Company Name",
  "position": "Job Title (if mentioned)",
  "summary": "A concise 1-sentence summary of the email",
  "next_step": "Action required by Hazal, e.g. Book interview slot by Friday, or None"
}}
"""


def _clean_header(val: str) -> str:
    """Decode encoded email headers (e.g. UTF-8 base64)."""
    if not val:
        return ""
    decoded_parts = decode_header(val)
    parts = []
    for content, encoding in decoded_parts:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(content))
    return "".join(parts)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disp:
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="replace") + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    return body.strip()


def classify_email_with_gemini(sender: str, subject: str, date: str, body: str) -> dict:
    """Send email snippet to Gemini 1.5 Flash for classification."""
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set.")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-3.6-flash")

    prompt = _CLASSIFIER_PROMPT.format(
        sender=sender,
        subject=subject,
        date=date,
        body=body[:2000] if body else "(No text content)",
    )

    response = model.generate_content(prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Gemini classification JSON: %s", raw)
        return {
            "is_job_related": False,
            "category": "UNRELATED",
            "company": "",
            "summary": "Could not parse email",
            "next_step": "",
        }


def sync_gmail(days_back: int = 14) -> dict:
    """
    Connect to Gmail via IMAP, find application-related emails from the last N days,
    classify them with Gemini, and update job records in SQLite.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return {
            "success": False,
            "error": "GMAIL_USER veya GMAIL_APP_PASSWORD .env içinde ayarlanmamış.",
            "processed": 0,
            "updates": [],
        }

    updates = []
    since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%d-%b-%Y")

    try:
        logger.info("Connecting to Gmail IMAP for %s...", GMAIL_USER)
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        # Search query: look for emails from the last N days with keywords
        # in Subject or Body: application, interview, bewerbung, or job
        search_query = f'(SINCE "{since_date}")'
        status, message_numbers = mail.search(None, search_query)

        if status != "OK" or not message_numbers[0]:
            mail.logout()
            return {"success": True, "processed": 0, "updates": [], "message": "Yeni e-posta bulunamadı."}

        msg_ids = message_numbers[0].split()
        # Check the most recent 25 emails to stay fast and respect rate limits
        recent_ids = msg_ids[-25:]
        logger.info("Scanning %d recent emails...", len(recent_ids))

        for mid in reversed(recent_ids):
            _, data = mail.fetch(mid, "(RFC822)")
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _clean_header(msg.get("Subject", ""))
            sender = _clean_header(msg.get("From", ""))
            date_str = msg.get("Date", "")
            body = _extract_body(msg)

            # Quick pre-filter: skip if no keywords present in subject or sender
            keywords = ["application", "interview", "bewerbung", "status", "candidate", "karriere", "careers", "position"]
            has_kw = any(kw in subject.lower() or kw in sender.lower() for kw in keywords)
            if not has_kw:
                continue

            # Classify with Gemini
            analysis = classify_email_with_gemini(sender, subject, date_str, body)
            if not analysis.get("is_job_related") or analysis.get("category") == "UNRELATED":
                continue

            company = analysis.get("company", "")
            category = analysis.get("category", "RECEIVED")
            summary = analysis.get("summary", "")

            # Match with a job in DB
            matched_job = find_job_by_company(company) if company else None

            status_map = {
                "INTERVIEW": "interview",
                "REJECTED": "rejected",
                "ASSESSMENT": "assessment",
            }
            new_status = status_map.get(category)

            update_info = {
                "subject": subject,
                "sender": sender,
                "company": company,
                "category": category,
                "summary": summary,
                "matched_job": matched_job["title"] if matched_job else None,
                "matched_company": matched_job["company"] if matched_job else company,
                "db_updated": False,
            }

            if matched_job and new_status:
                note = f"[{category}] {summary} (E-posta: {date_str[:16]})"
                update_job_from_email(matched_job["id"], new_status, note)
                update_info["db_updated"] = True

            updates.append(update_info)

        mail.logout()
        return {
            "success": True,
            "processed": len(recent_ids),
            "updates": updates,
        }

    except Exception as exc:
        logger.error("Gmail sync failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "processed": 0,
            "updates": [],
        }
