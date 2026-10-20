import logging
from difflib import get_close_matches

from telegram import BotCommand, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Registered with Telegram on startup so typing "/" pops up the command list.
# Keep in sync with help_command below.
BOT_COMMANDS = [
    BotCommand("menu", "🔎 Pick what to search from buttons"),
    BotCommand("movie", "🎬 Search for a movie to add"),
    BotCommand("show", "📺 Search for a TV show to add"),
    BotCommand("anime", "🎌 Search for anime to add"),
    BotCommand("mymovies", "🎬 List movies in the library"),
    BotCommand("myshows", "📺 List TV shows in the library"),
    BotCommand("myanime", "🎌 List anime in the library"),
    BotCommand("addmovie", "🎬 Add the top match for a movie title"),
    BotCommand("addshow", "📺 Search for a show by title"),
    BotCommand("managemovie", "⚙️ Monitor, unmonitor or remove a movie"),
    BotCommand("manageshow", "⚙️ Monitor seasons of, or remove, a TV show"),
    BotCommand("manageanime", "⚙️ Monitor seasons of, or remove, an anime"),
    BotCommand("imports", "📥 Downloads waiting on a manual import"),
    BotCommand("whatsnew", "🆕 See what changed in the latest update"),
    BotCommand("help", "ℹ️ Show the command list"),
    BotCommand("start", "👋 Show the welcome message and buttons"),
    BotCommand("hide", "⌨️ Hide the button keyboard"),
    BotCommand("version", "🏷️ Show which version is running"),
]

# Telegram hard-caps a single message at 4096 characters.
_TELEGRAM_MAX = 4000

# How many library matches the manage commands offer as buttons.
MAX_LIBRARY_MATCHES = 10


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


def is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Owners are the ALLOWED_USERS — not everyone in an allowed group.

    Gates the irreversible actions (removing media, deleting files) and
    broadcasting, which group members shouldn't be able to do.
    """
    user = update.effective_user
    return bool(user and user.id in context.bot_data.get("allowed_users", []))


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


def format_size(num_bytes: int) -> str:
    """Human-readable size, e.g. 4.2 GB."""
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def find_in_library(query: str, *pools: list[dict]) -> list[dict]:
    """Match a typed title against library entries, best match first.

    Pools are searched in order of preference — e.g. anime, then the whole
    library for /manageanime. Every pool gets a substring pass before any gets a
    fuzzy one, so a real match in a later pool beats a near-miss in an earlier
    one. Substring hits rank exact title, then prefix, then the rest; fuzzy hits
    keep difflib's closeness order, so "brekaing bad" still lands.

    Returns every match; callers decide how many to show.
    """
    needle = query.casefold().strip()

    def title(item: dict) -> str:
        return (item.get("title") or "").casefold()

    for pool in pools:
        hits = [i for i in pool if needle in title(i)]
        if hits:
            hits.sort(key=lambda i: (title(i) != needle, not title(i).startswith(needle),
                                     (i.get("sortTitle") or "").lower()))
            return hits

    for pool in pools:
        # A list per title: remakes and same-named films must all survive.
        by_title: dict[str, list[dict]] = {}
        for i in pool:
            by_title.setdefault(title(i), []).append(i)
        close = get_close_matches(needle, list(by_title), n=10, cutoff=0.6)
        if close:
            return [i for t in close for i in by_title[t]]

    return []


def which_one_text(question: str, total: int) -> str:
    """Heading for a list of library matches, saying so when some were cut off."""
    if total <= MAX_LIBRARY_MATCHES:
        return question
    return f"{question}\n\nShowing the best {MAX_LIBRARY_MATCHES} of {total} matches — type more of the title to narrow it down."


async def safe_edit(query, text: str, reply_markup=None) -> None:
    """Edit a button's message, ignoring Telegram's "message is not modified" on double-taps."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    logger.info(f"start_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"start_command: No message in update")
        return
    
    # Imported here rather than at module scope: menu_handlers imports this
    # module, so a top-level import would be circular.
    from app.handlers.menu_handlers import _send_with_quick_keyboard

    user_name = update.effective_user.first_name or "User"

    welcome_message = (
        f"👋 Welcome {user_name}!\n\n"
        "I add movies, TV shows and anime to the media server.\n\n"
        "Use the buttons below the text box — /menu walks you through a search "
        "without typing anything. You can also type a command directly, "
        "like /movie Dune.\n\n"
        "/help for everything, /hide to put the buttons away."
    )

    await _send_with_quick_keyboard(update, welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    logger.info(f"help_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"help_command: No message in update")
        return
    
    help_message = (
        "📖 **Available Commands**\n\n"
        "🔎 **Easiest way**:\n"
        "  /menu - Pick what to search from buttons, no typing\n"
        "  /start - Show the button keyboard under the text box\n"
        "  /hide - Put that keyboard away again\n"
        "  /whatsnew - What changed in the latest update\n"
        "  /version - Which version is running\n\n"
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
        "⚙️ **Manage your library**:\n"
        "  /managemovie <title> - Monitor, unmonitor, search or remove a movie\n"
        "  /manageshow <title> - Same for a show, plus per-season monitoring\n"
        "  /manageanime <title> - Same for an anime\n"
        "  Removing (owners only) asks whether to also delete the files from the drive.\n\n"
        "📥 **Stuck downloads**:\n"
        "  /imports - Downloads Sonarr/Radarr won't import without help\n"
        "  The bot also alerts the owners when one appears, with buttons to\n"
        "  review the files, import anyway, or reject and search again.\n\n"
        "💡 **Inline Queries** (use in any chat):\n"
        "  @YourBotName movie <title> - Search movies\n"
        "  @YourBotName show <title> - Search TV shows\n"
        "  @YourBotName anime <title> - Search anime\n\n"
        "💡 **Tips**:\n"
        "  • Tap a command from the / list without typing a title — I'll ask for one\n"
        "  • /menu is the quickest way — just tap and reply\n"
        "  • Searching for something already in the library offers ⚙️ Manage instead of Add\n"
        "  • Inline queries work in any chat, but only for the bot's owners\n"
        "  • Anime goes to your anime folder, shows go to your shows folder\n"
    )
    
    await update.message.reply_text(help_message, parse_mode="Markdown")
