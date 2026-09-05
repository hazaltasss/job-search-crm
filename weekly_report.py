"""
weekly_report.py — Standalone script for the Monday weekly digest.
Executed by GitHub Actions cron (Monday 08:00 CET).
"""
import logging
import sys

from rich.logging import RichHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("📬 Generating weekly report...")
    try:
        from src.database import init_db
        from src.analytics import build_weekly_report
        from src.telegram_bot import send_text

        init_db()
        report = build_weekly_report()
        send_text(report)
        logger.info("✅ Weekly report sent to Telegram.")
    except Exception as exc:
        logger.error("Weekly report failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
