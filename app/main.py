"""
Main bot application entry point.
Initializes and runs the Telegram bot with command handlers.
"""

import logging
import sys
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters

from app.config.settings import settings
from app.clients.sonarr import SonarrClient
from app.clients.radarr import RadarrClient
from app.handlers.general_handlers import start_command, help_command
from app.handlers.radarr_handlers import movie_command, add_movie_command, button_add_movie, inline_query_radarr, my_movies_command
from app.handlers.sonarr_handlers import show_command, add_show_command, button_add_show, button_monitor_show, button_add_anime, button_monitor_anime, inline_query_sonarr, anime_command, inline_query_anime, my_shows_command, my_anime_command

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level.upper(), logging.INFO)
)
# httpx logs full request URLs at INFO, which embed the bot token — keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    """Log errors and continue processing updates."""
    logger.error(f"Update {update} caused error: {context.error}")
    if update and update.message:
        try:
            await update.message.reply_text("❌ An error occurred processing your request.")
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    elif update and update.callback_query:
        try:
            await update.callback_query.answer("❌ An error occurred.", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to send callback error: {e}")


async def log_update(update, context):
    """Log all incoming updates for debugging."""
    if update.message:
        logger.debug(f"Received message from {update.effective_user.id} in chat {update.message.chat_id}: {update.message.text}")
    elif update.callback_query:
        logger.debug(f"Received callback from {update.effective_user.id}: {update.callback_query.data}")
    elif update.inline_query:
        logger.debug(f"Received inline query from {update.effective_user.id}: {update.inline_query.query}")
    return False


def main() -> None:
    """Start the bot."""
    try:
        # Initialize API clients
        sonarr_client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        radarr_client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
        
        # Close the shared HTTP sessions cleanly on shutdown
        async def _post_shutdown(app) -> None:
            await sonarr_client.close()
            await radarr_client.close()

        # Create the Application
        application = Application.builder().token(settings.telegram_token).post_shutdown(_post_shutdown).build()
        
        # Store clients and allowed users in bot_data
        application.bot_data["sonarr_client"] = sonarr_client
        application.bot_data["radarr_client"] = radarr_client
        application.bot_data["allowed_users"] = settings.allowed_user_ids
        
        # Register command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # Radarr handlers
        application.add_handler(CommandHandler("movie", movie_command))
        application.add_handler(CommandHandler("addmovie", add_movie_command))
        application.add_handler(CommandHandler("mymovies", my_movies_command))
        application.add_handler(CallbackQueryHandler(button_add_movie, pattern=r'^add_movie:'))
        application.add_handler(InlineQueryHandler(inline_query_radarr, pattern=r'(?i)^movie\s'))

        # Sonarr handlers
        application.add_handler(CommandHandler("show", show_command))
        application.add_handler(CommandHandler("addshow", add_show_command))
        application.add_handler(CommandHandler("myshows", my_shows_command))
        application.add_handler(CallbackQueryHandler(button_add_show, pattern=r'^select_show:'))
        application.add_handler(CallbackQueryHandler(button_monitor_show, pattern=r'^monitor_show_'))
        application.add_handler(InlineQueryHandler(inline_query_sonarr, pattern=r'(?i)^show\s'))

        # Anime handlers
        application.add_handler(CommandHandler("anime", anime_command))
        application.add_handler(CommandHandler("myanime", my_anime_command))
        application.add_handler(CallbackQueryHandler(button_add_anime, pattern=r'^select_anime:'))
        application.add_handler(CallbackQueryHandler(button_monitor_anime, pattern=r'^monitor_anime_'))
        application.add_handler(InlineQueryHandler(inline_query_anime, pattern=r'(?i)^anime\s'))
        
        # Add debug logging handler - logs all messages before they're processed (group -1 = before other handlers)
        application.add_handler(MessageHandler(filters.ALL, log_update), group=-1)
        
        # Add error handler to catch and log errors
        application.add_error_handler(error_handler)
        
        logger.info("Bot started successfully!")
        logger.info(f"Allowed users: {settings.allowed_user_ids}")
        
        # Start the Bot
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
