import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

BOT_TOKEN: str = os.environ["BOT_TOKEN"]  # hard-fail if missing

MINI_APP_URL: str = os.environ.get(
    "MINI_APP_URL",
    "https://localhost:8000/static/index.html",
)

WEBHOOK_URL: str | None = os.environ.get("WEBHOOK_URL")  # e.g. https://myapp.railway.app/webhook
PORT: int = int(os.environ.get("PORT", "8080"))

# ---------------------------------------------------------------------------
# /start handler
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 <b>NutriOS ga xush kelibsiz!</b>\n\n"
    "🥗 Ovqatlaringizni kuzating, suvingizni hisoblang va "
    "kunlik maqsadlaringizga erishing.\n\n"
    "Boshlash uchun quyidagi tugmani bosing 👇"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with the Mini App launch button."""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🥗 NutriOS ni ochish",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]
        ]
    )

    await update.message.reply_html(
        text=WELCOME_TEXT,
        reply_markup=keyboard,
    )
    logger.info("Sent Mini App button to user %s", update.effective_user.id)


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    return app


# ---------------------------------------------------------------------------
# Entry point — webhook (Railway) or polling (local dev)
# ---------------------------------------------------------------------------

def main() -> None:
    application = build_application()

    if WEBHOOK_URL:
        # Production: Railway sets PORT and WEBHOOK_URL
        logger.info("Starting webhook on port %d → %s", PORT, WEBHOOK_URL)
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            drop_pending_updates=True,  # ignore queued updates from downtime
        )
    else:
        # Local development: simple long-polling, no public URL needed
        logger.info("WEBHOOK_URL not set — starting polling mode")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
