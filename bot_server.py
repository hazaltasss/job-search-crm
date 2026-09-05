"""
bot_server.py — Long-polling bot listener.

Run this locally (or on a VPS / Railway / Fly.io) to receive and respond
to Telegram inline button callbacks in real time.

The GitHub Actions cron job (main.py) sends new job notifications.
This server handles the interactive button responses (Applied, Skip, etc.)

Usage:
    python bot_server.py
"""
import logging
import sys

from rich.logging import RichHandler

# ─── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        from src.database import init_db
        from src.telegram_bot import build_application
    except ImportError as exc:
        logger.error("Import error: %s\nRun: pip install -r requirements.txt", exc)
        sys.exit(1)

    # Ensure database is ready
    init_db()

    logger.info("🤖 Starting Job Search CRM Bot (long-polling mode)...")
    logger.info("Press Ctrl+C to stop.")

    app = build_application()
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
