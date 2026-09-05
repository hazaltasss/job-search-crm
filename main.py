"""
main.py — Primary entry point for the automated job fetch pipeline.

Executed by GitHub Actions cron (twice daily: 09:00 & 18:00 CET).
Flow:
  1. Initialise SQLite database
  2. Fetch jobs from HiringCafe + WorkingStudentJobs.de
  3. Run the filter pipeline (location, language, category)
  4. Deduplicate against the local database
  5. Append new jobs to Google Sheets
  6. Send Telegram notifications with inline buttons
  7. Log a run summary
"""
import logging
import sys
from datetime import datetime, timezone

from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger(__name__)
console = Console()


def main() -> None:
    run_start = datetime.now(timezone.utc)
    console.rule("[bold blue]Job Search CRM — Fetch Run")
    logger.info("Run started at %s UTC", run_start.strftime("%Y-%m-%d %H:%M:%S"))

    # ── Step 1: Init DB ───────────────────────────────────────────────────────
    try:
        from src.database import init_db
        init_db()
    except Exception as exc:
        logger.error("Database init failed: %s", exc)
        sys.exit(1)

    # ── Step 2: Fetch ─────────────────────────────────────────────────────────
    raw_jobs = []
    fetch_errors = []

    # 2a. Arbeitnow API (Free, reliable, full descriptions)
    try:
        from src.fetchers.arbeitnow import fetch_jobs as fetch_arbeitnow
        an_jobs = fetch_arbeitnow(max_pages=8)
        raw_jobs.extend(an_jobs)
        logger.info("Arbeitnow: %d raw jobs fetched", len(an_jobs))
    except Exception as exc:
        logger.error("Arbeitnow fetch failed: %s", exc)
        fetch_errors.append(f"Arbeitnow: {exc}")

    # 2b. WorkingStudentJobs.de (Berlin specific)
    try:
        from src.fetchers.workingstudentjobs import fetch_jobs as fetch_wsj
        wsj_jobs = fetch_wsj(max_pages=2)
        raw_jobs.extend(wsj_jobs)
        logger.info("WorkingStudentJobs: %d raw jobs fetched", len(wsj_jobs))
    except Exception as exc:
        logger.error("WorkingStudentJobs fetch failed: %s", exc)
        fetch_errors.append(f"WorkingStudentJobs: {exc}")

    if not raw_jobs:
        msg = "No raw jobs fetched from any source."
        logger.warning(msg)
        return

    # ── Step 3: Filter ────────────────────────────────────────────────────────
    from src.filters import filter_jobs
    filtered_jobs = filter_jobs(raw_jobs)
    logger.info(
        "Filtering: %d raw → %d matched", len(raw_jobs), len(filtered_jobs)
    )

    # ── Step 4: Deduplicate ───────────────────────────────────────────────────
    from src import database
    new_jobs = [j for j in filtered_jobs if not database.is_duplicate(j.url)]
    logger.info(
        "Deduplication: %d matched → %d new (not seen before)",
        len(filtered_jobs), len(new_jobs),
    )

    if not new_jobs:
        logger.info("No new jobs to send. All matching jobs are already in database.")
        return

    # ── Step 5: Store in DB & Optional Sheet / Telegram Sync ──────────────────
    import os
    telegram_enabled = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_BOT_TOKEN") not in ("__skip__", "__not_configured__", "your_telegram_bot_token_here"))
    sheets_enabled = bool(os.getenv("GOOGLE_SHEET_ID") and os.getenv("GOOGLE_SHEET_ID") not in ("__skip__", "__not_configured__", "your_google_sheet_id_here"))

    if sheets_enabled:
        from src import sheets as gsheets
        try:
            gsheets.ensure_headers()
        except Exception as exc:
            logger.warning("Could not verify sheet headers: %s", exc)
            sheets_enabled = False

    sent_count = 0
    saved_count = 0
    errors = []

    for job in new_jobs:
        try:
            # 5a. Always store in database
            db_id = database.insert_job(job)
            job.db_id = db_id
            saved_count += 1

            # 5b. Append to Google Sheets (if configured)
            if sheets_enabled:
                try:
                    sheet_row = gsheets.append_job(job)
                    job.sheet_row = sheet_row
                    database.update_sheet_row(db_id, sheet_row)
                except Exception as sheet_exc:
                    logger.warning("Sheet append failed for '%s': %s", job.title, sheet_exc)

            # 5c. Send Telegram notification (if configured)
            if telegram_enabled:
                from src.telegram_bot import send_job_alert
                send_job_alert(job, db_id)
                sent_count += 1

        except Exception as exc:
            logger.error("Failed to process job '%s': %s", job.title, exc)
            errors.append(job.title)

    # ── Step 6: Summary ───────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - run_start).total_seconds()

    # Print summary table to console
    table = Table(title="Fetch Run Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="bold green")
    table.add_row("Raw jobs fetched", str(len(raw_jobs)))
    table.add_row("Passed filters",   str(len(filtered_jobs)))
    table.add_row("New (unique)",      str(len(new_jobs)))
    table.add_row("Notifications sent", str(sent_count))
    table.add_row("Errors",            str(len(errors)))
    table.add_row("Elapsed",           f"{elapsed:.1f}s")
    console.print(table)

    if errors:
        logger.warning("Failed jobs: %s", ", ".join(errors))

    # Send a summary to Telegram if no individual alerts were sent
    if sent_count == 0 and not errors:
        try:
            send_text(
                "📭 <b>Job Search Run Complete</b>\n"
                f"No new matching jobs found in this scan.\n"
                f"({len(raw_jobs)} total scraped, {len(filtered_jobs)} passed filters, all already seen)"
            )
        except Exception:
            pass

    logger.info("✅ Done! Sent %d new job alerts in %.1fs.", sent_count, elapsed)


if __name__ == "__main__":
    main()
