"""
Telegram bot: message formatting, inline buttons, and callback handlers.

Two modes of operation:
  1. NOTIFY MODE (used by main.py / GitHub Actions):
     - Standalone: creates a Bot instance and sends messages, then exits.
     - No long-running process needed.

  2. LISTENER MODE (used by bot_server.py, run locally):
     - Runs long-polling to receive button callback queries from users.
     - Handles: Applied, Skip, Save, Cover Letter, Tailor CV actions.
"""
from __future__ import annotations
import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from src.models import Job

logger = logging.getLogger(__name__)

# ─── Callback Data Format: "{action}:{db_id}" ─────────────────────────────────
ACTION_APPLIED   = "applied"
ACTION_SKIP      = "skip"
ACTION_SAVE      = "save"
ACTION_COVER     = "cover"
ACTION_TAILOR_CV = "tailor_cv"


# ─── Message Formatting ────────────────────────────────────────────────────────

def _format_job_message(job: Job) -> str:
    location_display = job.short_location
    remote_badge = " 🏠 Remote" if job.is_remote else ""
    category_badge = f"🏷️ {job.category}" if job.category else ""
    score_bar = "⭐" * (job.match_score // 25 + 1)

    return (
        f"🚨 <b>New Matching Job Found!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Position:</b> {job.title}\n"
        f"🏢 <b>Company:</b> {job.company}\n"
        f"📍 <b>Location:</b> {location_display}{remote_badge}\n"
        f"🌐 <b>Language:</b> English\n"
        f"{f'{category_badge}   ' if category_badge else ''}"
        f"<b>Match:</b> {score_bar} ({job.match_score}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def _build_keyboard(db_id: int, url: str) -> InlineKeyboardMarkup:
    """Build the 3-row inline keyboard for a job notification."""
    return InlineKeyboardMarkup([
        # Row 1: View listing
        [InlineKeyboardButton("🔗 View Job Listing", url=url)],
        # Row 2: Status tracking
        [
            InlineKeyboardButton("✅ Applied",          callback_data=f"{ACTION_APPLIED}:{db_id}"),
            InlineKeyboardButton("❌ Skip",              callback_data=f"{ACTION_SKIP}:{db_id}"),
            InlineKeyboardButton("⏳ Save for Later",    callback_data=f"{ACTION_SAVE}:{db_id}"),
        ],
        # Row 3: AI tools
        [
            InlineKeyboardButton("📝 Cover Letter",     callback_data=f"{ACTION_COVER}:{db_id}"),
            InlineKeyboardButton("📄 Tailor My CV",     callback_data=f"{ACTION_TAILOR_CV}:{db_id}"),
        ],
    ])


# ─── Notify Mode (fire-and-forget, used by main.py) ───────────────────────────

async def _send_job_alert_async(job: Job, db_id: int) -> None:
    from src.config import _validate
    token   = _validate("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN, "Telegram notifications")
    chat_id = _validate("TELEGRAM_CHAT_ID",   TELEGRAM_CHAT_ID,   "Telegram notifications")
    bot = Bot(token=token)
    text = _format_job_message(job)
    keyboard = _build_keyboard(db_id, job.url)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    logger.info("Sent Telegram alert for job db_id=%d: %s", db_id, job.title)


def send_job_alert(job: Job, db_id: int) -> None:
    """Send a job notification message (synchronous wrapper)."""
    asyncio.run(_send_job_alert_async(job, db_id))


async def _send_text_async(text: str, parse_mode: str = ParseMode.HTML) -> None:
    from src.config import _validate
    token   = _validate("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN, "Telegram notifications")
    chat_id = _validate("TELEGRAM_CHAT_ID",   TELEGRAM_CHAT_ID,   "Telegram notifications")
    bot = Bot(token=token)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )


def send_text(text: str) -> None:
    """Send a plain text or HTML message to the user (synchronous wrapper)."""
    asyncio.run(_send_text_async(text))


async def _send_document_async(file_path: str, caption: str = "") -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    with open(file_path, "rb") as f:
        await bot.send_document(
            chat_id=TELEGRAM_CHAT_ID,
            document=f,
            caption=caption,
        )


def send_document(file_path: str, caption: str = "") -> None:
    """Send a file (e.g. .docx cover letter) to the user."""
    asyncio.run(_send_document_async(file_path, caption))


# ─── Listener Mode (used by bot_server.py) ────────────────────────────────────

async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline button presses to the correct handler."""
    query = update.callback_query
    await query.answer()  # Acknowledge the click (removes loading spinner)

    data = query.data or ""
    if ":" not in data:
        logger.warning("Unexpected callback data: %s", data)
        return

    action, db_id_str = data.split(":", 1)
    db_id = int(db_id_str)

    # Import here to avoid circular imports at module load
    from src import database, sheets, ai_assistant

    job_row = database.get_job_by_db_id(db_id)
    if not job_row:
        await query.edit_message_text("⚠️ Job not found in database.")
        return

    job = Job(
        job_id=job_row["job_id"],
        source=job_row["source"],
        title=job_row["title"],
        company=job_row["company"],
        location=job_row["location"],
        url=job_row["url"],
        description=job_row.get("description", ""),
        is_remote=bool(job_row.get("is_remote", 0)),
        is_berlin=bool(job_row.get("is_berlin", 0)),
        category=job_row.get("category", ""),
        match_score=job_row.get("match_score", 0),
        db_id=db_id,
        sheet_row=job_row.get("sheet_row"),
        status=job_row.get("status", "new"),
    )

    # ── Status tracking actions ───────────────────────────────────────────────
    if action in (ACTION_APPLIED, ACTION_SKIP, ACTION_SAVE):
        status_map = {
            ACTION_APPLIED: ("applied",  "✅ Marked as <b>Applied</b>! Good luck! 🍀"),
            ACTION_SKIP:    ("skipped",  "❌ Job <b>skipped</b> and removed from your queue."),
            ACTION_SAVE:    ("saved",    "⏳ Job <b>saved for later</b>. You can review it anytime."),
        }
        new_status, confirmation = status_map[action]
        database.update_status(db_id, new_status)

        # Update Google Sheets if row is tracked
        if job.sheet_row:
            try:
                sheets.update_status(job.sheet_row, new_status)
            except Exception as exc:
                logger.error("Failed to update sheet: %s", exc)

        # Edit original message to show updated status
        original_text = query.message.text or ""
        updated_text = original_text + f"\n\n{confirmation}"
        try:
            await query.edit_message_text(
                text=updated_text[:4096],
                parse_mode=ParseMode.HTML,
                reply_markup=None,  # Remove buttons after action
            )
        except Exception:
            await query.message.reply_text(confirmation, parse_mode=ParseMode.HTML)

    # ── AI: Cover Letter ──────────────────────────────────────────────────────
    elif action == ACTION_COVER:
        await query.edit_message_text(
            text=query.message.text + "\n\n⏳ <i>Generating your cover letter... (usually 10–20s)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=query.message.reply_markup,
        )
        try:
            cover_letter = ai_assistant.generate_cover_letter(job)

            # Send as Telegram message (split if over 4096 chars)
            header = (
                f"📝 <b>Cover Letter for {job.title} @ {job.company}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            full_text = header + cover_letter

            if len(full_text) <= 4096:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=full_text,
                    parse_mode=ParseMode.HTML,
                )
            else:
                # Split into chunks
                chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
                for chunk in chunks:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                    )

            # Also save as .docx and send as file
            try:
                docx_path = ai_assistant.save_cover_letter_docx(cover_letter, job)
                with open(docx_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=f,
                        filename=docx_path.name,
                        caption=f"📄 Cover Letter — {job.title} @ {job.company}",
                    )
            except Exception as docx_err:
                logger.warning("Could not save .docx: %s", docx_err)

        except Exception as exc:
            logger.error("Cover letter generation failed: %s", exc)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⚠️ Cover letter generation failed: {exc}",
            )

    # ── AI: Tailor CV ─────────────────────────────────────────────────────────
    elif action == ACTION_TAILOR_CV:
        await query.edit_message_text(
            text=query.message.text + "\n\n⏳ <i>Analyzing job & tailoring your CV... (usually 15–25s)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=query.message.reply_markup,
        )
        try:
            cv_advice = ai_assistant.tailor_cv(job)
            header = (
                f"📄 <b>CV Tailoring Guide — {job.title} @ {job.company}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            full_text = header + cv_advice
            chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
            for chunk in chunks:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            logger.error("CV tailoring failed: %s", exc)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⚠️ CV tailoring failed: {exc}",
            )

    else:
        logger.warning("Unknown action: %s", action)


async def _handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /stats command."""
    from src.analytics import build_stats_message
    text = build_stats_message()
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show help and user's chat ID."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 <b>Job Search CRM Bot — Ready!</b>\n\n"
        f"Your Chat ID: <code>{chat_id}</code>\n"
        f"(Add this to your .env as TELEGRAM_CHAT_ID)\n\n"
        f"Available commands:\n"
        f"  /stats — View your application analytics\n"
        f"  /help  — Show this message",
        parse_mode=ParseMode.HTML,
    )


def build_application() -> Application:
    """Build and configure the Telegram Application (for bot_server.py)."""
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("help",  _handle_start))
    app.add_handler(CommandHandler("stats", _handle_stats))
    app.add_handler(CallbackQueryHandler(_handle_callback))
    return app
