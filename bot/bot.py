import asyncio
import logging
import os
import sys

from telegram.ext import ApplicationBuilder

from cleanup import cleanup_loop
from handlers import register_handlers

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def wait_for_bot_api(url: str, max_wait: int = 60):
    """Wait for the self-hosted Bot API server to become reachable."""
    import httpx
    for i in range(max_wait):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=2)
                logger.info("Bot API server ready (attempt %d)", i + 1)
                return
        except Exception:
            if i % 5 == 0:
                logger.info("Waiting for Bot API server at %s... (attempt %d)", url, i + 1)
            await asyncio.sleep(1)
    logger.warning("Bot API server not reachable after %ds, starting anyway", max_wait)


def main():
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN environment variable is required")
        sys.exit(1)

    api_url = os.environ.get("TELEGRAM_BOT_API_URL", "http://telegram-bot-api:8081")
    base_url = f"{api_url}/bot"
    base_file_url = f"{api_url}/file/bot"

    logger.info("Starting bot with API server: %s", api_url)

    asyncio.get_event_loop().run_until_complete(wait_for_bot_api(api_url))

    app = (
        ApplicationBuilder()
        .token(bot_token)
        .base_url(base_url)
        .base_file_url(base_file_url)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .build()
    )

    register_handlers(app)

    async def post_init(application):
        asyncio.create_task(cleanup_loop())
        from telegram import BotCommand
        await application.bot.set_my_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Help and commands"),
            BotCommand("mp3", "Download as MP3"),
            BotCommand("mp4", "Download best quality MP4"),
            BotCommand("best", "Best available quality"),
            BotCommand("platforms", "Supported platforms"),
            BotCommand("settings", "Your preferences"),
            BotCommand("setquality", "Set default quality"),
            BotCommand("setformat", "Set default format"),
            BotCommand("stats", "Bot statistics"),
        ])
        logger.info("Bot commands registered")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
