import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.message:
        return
    
    user_name = update.effective_user.first_name or "User"
    
    welcome_message = (
        f"👋 Welcome {user_name}!\n\n"
        "I'm a Telegram bot that helps you manage your media library.\n\n"
        "🎬 **Movies** (Radarr):\n"
        "  /movie <title> - Search for movies\n"
        "  /addmovie <title> - Add a movie\n"
        "  /mymovies - List monitored movies\n\n"
        "📺 **TV Shows** (Sonarr):\n"
        "  /show <title> - Search for TV shows\n"
        "  /addshow <title> - Add a TV show\n"
        "  /myshows - List monitored shows\n\n"
        "ℹ️ **Info**:\n"
        "  /help - Show this help message\n"
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not update.message:
        return
    
    help_message = (
        "📖 **Available Commands**\n\n"
        "🎬 **Radarr (Movies)**:\n"
        "  /movie <title> - Search for movies\n"
        "  /addmovie <title> - Add a movie to monitor\n"
        "  /mymovies - List all monitored movies\n\n"
        "📺 **Sonarr (TV Shows)**:\n"
        "  /show <title> - Search for TV shows\n"
        "  /addshow <title> - Add a TV show to monitor\n"
        "  /myshows - List all monitored shows\n\n"
        "💡 **Tips**:\n"
        "  • Use quotes for exact matches: /movie \"The Matrix\"\n"
        "  • Search results show IMDb/TMDb IDs for verification\n"
        "  • Only exact matches will be added to avoid duplicates\n"
    )
    
    await update.message.reply_text(help_message, parse_mode="Markdown")
