"""
Main bot application entry point.
Initializes and runs the Telegram bot with command handlers.
"""

import logging
import sys
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler

from app.config.settings import settings
from app.clients.sonarr import SonarrClient
from app.clients.radarr import RadarrClient
from app.handlers.general_handlers import start_command, help_command
from app.handlers.radarr_handlers import movie_command, add_movie_command, button_add_movie, inline_query_radarr
from app.handlers.sonarr_handlers import show_command, add_show_command, button_add_show, button_monitor_show, button_add_anime, button_monitor_anime, inline_query_sonarr, anime_command, inline_query_anime

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the bot."""
    try:
        # Initialize API clients
        sonarr_client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        radarr_client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
        
        # Create the Application
        application = Application.builder().token(settings.telegram_token).build()
        
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
        application.add_handler(CallbackQueryHandler(button_add_movie, pattern=r'^add_movie:'))
        application.add_handler(InlineQueryHandler(inline_query_radarr))
        
        # Sonarr handlers
        application.add_handler(CommandHandler("show", show_command))
        application.add_handler(CommandHandler("addshow", add_show_command))
        application.add_handler(CallbackQueryHandler(button_add_show, pattern=r'^select_show:'))
        application.add_handler(CallbackQueryHandler(button_monitor_show, pattern=r'^monitor_show_'))
        application.add_handler(InlineQueryHandler(inline_query_sonarr))
        
        # Anime handlers
        application.add_handler(CommandHandler("anime", anime_command))
        application.add_handler(CallbackQueryHandler(button_add_anime, pattern=r'^select_anime:'))
        application.add_handler(CallbackQueryHandler(button_monitor_anime, pattern=r'^monitor_anime_'))
        application.add_handler(InlineQueryHandler(inline_query_anime))
        
        logger.info("Bot started successfully!")
        logger.info(f"Allowed users: {settings.allowed_user_ids}")
        
        # Start the Bot
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
