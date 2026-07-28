import logging
from telegram import BotCommand, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Registered with Telegram on startup so typing "/" pops up the command list.
# Keep in sync with help_command below.
BOT_COMMANDS = [
    BotCommand("movie", "🎬 Search for a movie to add"),
    BotCommand("show", "📺 Search for a TV show to add"),
    BotCommand("anime", "🎌 Search for anime to add"),
    BotCommand("mymovies", "🎬 List movies in the library"),
    BotCommand("myshows", "📺 List TV shows in the library"),
    BotCommand("myanime", "🎌 List anime in the library"),
    BotCommand("addmovie", "🎬 Add the top match for a movie title"),
    BotCommand("addshow", "📺 Search for a show by title"),
    BotCommand("help", "ℹ️ Show the command list"),
    BotCommand("start", "👋 Show the welcome message"),
]

# Telegram hard-caps a single message at 4096 characters.
_TELEGRAM_MAX = 4000


def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Authorize by user ID, or by membership of an allowed group chat.

    Inline queries and buttons on inline-sent messages carry no chat, so those are
    always user-ID only — Telegram doesn't tell us which chat they came from.
    """
    user = update.effective_user
    if user and user.id in context.bot_data.get("allowed_users", []):
        return True

    chat = update.effective_chat
    if chat and chat.id in context.bot_data.get("allowed_chats", []):
        return True

    return False


async def reply_in_chunks(message, header: str, lines: list[str]) -> None:
    """Reply with a header followed by lines, splitting across messages if needed."""
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > _TELEGRAM_MAX:
            await message.reply_text(chunk)
            chunk = ""
        chunk += ("\n" if chunk else "") + line
    if chunk.strip():
        await message.reply_text(chunk)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    logger.info(f"start_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"start_command: No message in update")
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
        "🎌 **Anime** (Sonarr):\n"
        "  /anime <title> - Search for anime\n"
        "  /myanime - List monitored anime\n\n"
        "ℹ️ **Info**:\n"
        "  /help - Show this help message\n"
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    logger.info(f"help_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"help_command: No message in update")
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
        "🎌 **Anime (Sonarr)**:\n"
        "  /anime <title> - Search for anime\n"
        "  /myanime - List all monitored anime\n\n"
        "💡 **Inline Queries** (use in any chat):\n"
        "  @YourBotName movie <title> - Search movies\n"
        "  @YourBotName show <title> - Search TV shows\n"
        "  @YourBotName anime <title> - Search anime\n\n"
        "💡 **Tips**:\n"
        "  • Use quotes for exact matches: /movie \"The Matrix\"\n"
        "  • Inline queries work in any Telegram chat\n"
        "  • Anime goes to your anime folder, shows go to your shows folder\n"
    )
    
    await update.message.reply_text(help_message, parse_mode="Markdown")
