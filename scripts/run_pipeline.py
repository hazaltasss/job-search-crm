"""
run_pipeline.py — Primary entry point for the automated job fetch & ingestion pipeline.

Executed by GitHub Actions cron (twice daily: 09:00 & 18:00 CET) or manually.
Flow:
  1. Initialise SQLite database
  2. Fetch jobs from Arbeitnow + WorkingStudentJobs.de
  3. Run the filter pipeline (location, strict English language, category)
  4. Deduplicate against the local database
  5. Append new jobs to Google Sheets (if configured)
  6. Send Telegram notifications with inline buttons (if configured)
  7. Log a run summary
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

    # ── Step 2: Fetch (Concurrent across all 9 sources) ────────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.fetchers.arbeitnow import fetch_jobs as fetch_arbeitnow
    from src.fetchers.workingstudentjobs import fetch_jobs as fetch_wsj
    from src.fetchers.hiringcafe import fetch_jobs as fetch_hiringcafe
    from src.fetchers.linkedin import fetch_jobs as fetch_linkedin
    from src.fetchers.berlinstartupjobs import fetch_jobs as fetch_bsj
    from src.fetchers.greenhouse import fetch_jobs as fetch_greenhouse
    from src.fetchers.workwise import fetch_jobs as fetch_workwise
    from src.fetchers.personio import fetch_jobs as fetch_personio
    from src.fetchers.jobteaser import fetch_jobs as fetch_jobteaser

    fetcher_tasks = {
        "Arbeitnow": lambda: fetch_arbeitnow(max_pages=8),
        "WorkingStudentJobs": lambda: fetch_wsj(max_pages=2),
        "HiringCafe": lambda: fetch_hiringcafe(),
        "LinkedIn": lambda: fetch_linkedin(),
        "BerlinStartupJobs": lambda: fetch_bsj(),
        "Greenhouse": lambda: fetch_greenhouse(),
        "Workwise": lambda: fetch_workwise(),
        "Personio": lambda: fetch_personio(),
        "JobTeaser": lambda: fetch_jobteaser(),
    }

    raw_jobs = []
    fetch_errors = []
    source_counts = {}

    with ThreadPoolExecutor(max_workers=9) as pool:
        futures = {
            pool.submit(fn): name
            for name, fn in fetcher_tasks.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result()
                raw_jobs.extend(jobs)
                source_counts[name] = len(jobs)
                logger.info("%s: %d raw jobs fetched", name, len(jobs))
            except Exception as exc:
                logger.error("%s fetch failed: %s", name, exc)
                fetch_errors.append(f"{name}: {exc}")
                source_counts[name] = 0

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
    seen_batch_keys = set()
    new_jobs = []
    for j in filtered_jobs:
        # Check against local database
        if database.is_duplicate(j.url, title=j.title, company=j.company):
            continue
        # Check within current batch
        batch_key = (database.normalize_company(j.company), database.normalize_title(j.title))
        if batch_key in seen_batch_keys:
            continue
        seen_batch_keys.add(batch_key)
        new_jobs.append(j)

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
    table.add_column("Metric / Source", style="cyan")
    table.add_column("Count", style="bold green")
    for src_name, count in sorted(source_counts.items()):
        table.add_row(f"  • {src_name}", str(count))
    table.add_row("Total raw fetched", str(len(raw_jobs)))
    table.add_row("Passed filters",   str(len(filtered_jobs)))
    table.add_row("New (unique)",      str(len(new_jobs)))
    table.add_row("Notifications sent", str(sent_count))
    table.add_row("Errors",            str(len(errors) + len(fetch_errors)))
    table.add_row("Elapsed",           f"{elapsed:.1f}s")
    console.print(table)

    if errors:
        logger.warning("Failed jobs: %s", ", ".join(errors))

    # Send a summary to Telegram if no individual alerts were sent
    if sent_count == 0 and not errors and telegram_enabled:
        try:
            from src.telegram_bot import send_text
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
