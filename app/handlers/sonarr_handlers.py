import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.ext import ContextTypes

from app.clients.sonarr import SonarrClient
from app.config.settings import settings
from app.handlers.general_handlers import is_authorized, reply_in_chunks

logger = logging.getLogger(__name__)

# Monitor type labels matching Sonarr UI
MONITOR_OPTIONS = {
    "all": "📺 All Episodes",
    "future": "🔮 Future Episodes",
    "missing": "❌ Missing Episodes",
    "existing": "✅ Existing Episodes",
    "recent": "🕐 Recent Episodes",
    "pilot": "🎬 Pilot Episode",
    "first": "🎞️ First Season",
    "last": "⏱️ Last Season",
    "specials": "🎪 Monitor Specials",
    "no_specials": "🚫 Unmonitor Specials",
    "none": "⛔ None"
}

MONITOR_ORDER = ["all", "future", "missing", "existing", "recent", "pilot", "first", "last", "specials", "no_specials", "none"]


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /show command to search for TV shows."""
    logger.info(f"show_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"show_command: No message in update")
        return
    
    if not is_authorized(update, context):
        logger.warning(f"show_command: User {update.effective_user.id} not in allowed users")
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        logger.info(f"show_command: No arguments provided")
        await update.message.reply_text("Please provide a show name. Usage: /show <show_name>")
        return

    show_name = " ".join(context.args)
    client: SonarrClient = context.bot_data.get("sonarr_client")
    
    if not client:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return
    
    try:
        shows = await client.search_series(show_name)
        
        if not shows:
            await update.message.reply_text(f"No shows found for '{show_name}'")
            return
        
        # Store search results and create keyboard
        keyboard = []
        for show in shows[:10]:  # Limit to 10 results
            tvdb_id = show.get("tvdbId", show.get("id"))
            title = show.get("title", "Unknown")
            
            # Store show data for later retrieval
            data_key = f"show_{tvdb_id}"
            context.user_data[data_key] = {
                "title": title,
                "tvdb_id": tvdb_id,
                "year": show.get("year", ""),
                "overview": show.get("overview", "")
            }
            
            keyboard.append([InlineKeyboardButton(title, callback_data=f"select_show:{tvdb_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a show:", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error searching shows: {e}")
        await update.message.reply_text(f"Error searching shows: {str(e)}")


async def button_add_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display monitoring options for selected show."""
    query = update.callback_query
    
    if not query or not query.data:
        logger.warning("Received callback query without data in button_add_show")
        return
    
    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        await query.answer()

        tvdb_id = query.data.split(":")[1]
        data_key = f"show_{tvdb_id}"
        show_data = context.user_data.get(data_key, {})
        title = show_data.get("title", "Unknown")

        # Store tvdb_id for the next callback
        context.user_data["pending_show_tvdb_id"] = tvdb_id

        # Create monitoring options keyboard
        keyboard = []
        for monitor_type in MONITOR_ORDER:
            label = MONITOR_OPTIONS[monitor_type]
            keyboard.append([InlineKeyboardButton(label, callback_data=f"monitor_show_{monitor_type}:{tvdb_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"Select monitoring type for '{title}':",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in button_add_show: {e}")
        try:
            await query.answer("❌ An error occurred.", show_alert=True)
        except Exception as inner_e:
            logger.error(f"Failed to send error to user: {inner_e}")


async def _add_from_monitor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime: bool) -> None:
    """Shared handler for the monitor-type buttons; adds the series to Sonarr."""
    query = update.callback_query
    kind = "anime" if anime else "show"

    if not query or not query.data:
        logger.warning(f"Received callback query without data in button_monitor_{kind}")
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        await query.answer()

        # Parse callback data: monitor_<kind>_<type>:<tvdb_id>
        tvdb_id = int(query.data.split(":")[1])
        monitor_type = query.data.split("_", 2)[2].split(":")[0]

        if monitor_type not in MONITOR_OPTIONS:
            logger.warning(f"Unknown monitor type in callback: {monitor_type}")
            await query.answer("❌ Unknown monitoring option.", show_alert=True)
            return

        data_key = f"{kind}_{tvdb_id}"
        title = context.user_data.get(data_key, {}).get("title", "Unknown")

        client: SonarrClient = context.bot_data.get("sonarr_client")
        if not client:
            await query.answer("❌ Sonarr client not initialized.", show_alert=True)
            return

        result = await client.add_series(
            series_id=tvdb_id,
            title=title,
            root_folder_path=settings.sonarr_root_anime if anime else settings.sonarr_root_shows,
            quality_profile_id=settings.quality_profile_id,
            monitor_seasons=monitor_type,
            series_type="Anime" if anime else "Standard",
        )

        label = kind.capitalize()
        monitor_label = MONITOR_OPTIONS[monitor_type]

        if not result:
            await query.edit_message_text(text=f"❌ Error adding {kind}")
            return

        logger.info(f"Added {kind} {tvdb_id} ({title}) with monitoring type: {monitor_type}")

        # Sonarr kicks off the search itself via addOptions.searchForMissingEpisodes,
        # scoped to this series — no library-wide search needed.
        text = f"✅ {label} '{title}' added with monitoring: {monitor_label}"
        if SonarrClient.SEARCH_ON_ADD.get(monitor_type, True):
            text += "\n🔍 Searching for episodes now!"
        await query.edit_message_text(text=text)

    except Exception as e:
        logger.error(f"Error adding {kind}: {e}")
        try:
            await query.edit_message_text(text=f"❌ Error adding {kind}: {str(e)}")
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")


async def button_monitor_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle show monitoring option selection and add series."""
    await _add_from_monitor_callback(update, context, anime=False)


async def add_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addshow command."""
    await show_command(update, context)


async def _list_series(update: Update, context: ContextTypes.DEFAULT_TYPE, anime: bool) -> None:
    """Shared lister for /myshows and /myanime, split by series type."""
    if not update.message:
        return

    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return

    series = await client.get_monitored_series()
    filtered = [s for s in series if (s.get("seriesType", "").lower() == "anime") == anime]

    emoji = "🎌" if anime else "📺"
    label = "anime" if anime else "shows"
    if not filtered:
        await update.message.reply_text(f"{emoji} No {label} in your Sonarr library yet.")
        return

    filtered.sort(key=lambda s: (s.get("sortTitle") or s.get("title") or "").lower())
    lines = [
        f"{'✅' if s.get('statistics', {}).get('episodeFileCount', 0) else '⏳'} "
        f"{s.get('title', 'Unknown')} ({s.get('year', 'N/A')})"
        for s in filtered
    ]
    await reply_in_chunks(update.message, f"{emoji} Your {label} ({len(filtered)}):\n", lines)


async def my_shows_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /myshows command to list standard TV shows in Sonarr."""
    logger.info(f"my_shows_command called from user {update.effective_user.id}")
    await _list_series(update, context, anime=False)


async def my_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /myanime command to list anime in Sonarr."""
    logger.info(f"my_anime_command called from user {update.effective_user.id}")
    await _list_series(update, context, anime=True)


async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /anime command to search for anime."""
    logger.info(f"anime_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"anime_command: No message in update")
        return
    
    if not is_authorized(update, context):
        logger.warning(f"anime_command: User {update.effective_user.id} not in allowed users")
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        logger.info(f"anime_command: No arguments provided")
        await update.message.reply_text("Please provide an anime name. Usage: /anime <anime_name>")
        return

    anime_name = " ".join(context.args)
    client: SonarrClient = context.bot_data.get("sonarr_client")
    
    if not client:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return
    
    try:
        anime_shows = await client.search_series(anime_name)
        
        if not anime_shows:
            await update.message.reply_text(f"No anime found for '{anime_name}'")
            return
        
        # Store search results and create keyboard
        keyboard = []
        for anime in anime_shows[:10]:  # Limit to 10 results
            tvdb_id = anime.get("tvdbId", anime.get("id"))
            title = anime.get("title", "Unknown")
            
            # Store anime data for later retrieval
            data_key = f"anime_{tvdb_id}"
            context.user_data[data_key] = {
                "title": title,
                "tvdb_id": tvdb_id,
                "year": anime.get("year", ""),
                "overview": anime.get("overview", "")
            }
            
            keyboard.append([InlineKeyboardButton(title, callback_data=f"select_anime:{tvdb_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select an anime:", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error searching anime: {e}")
        await update.message.reply_text(f"Error searching anime: {str(e)}")


async def button_add_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display monitoring options for selected anime."""
    query = update.callback_query
    
    if not query or not query.data:
        logger.warning("Received callback query without data in button_add_anime")
        return
    
    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        await query.answer()

        tvdb_id = query.data.split(":")[1]
        data_key = f"anime_{tvdb_id}"
        anime_data = context.user_data.get(data_key, {})
        title = anime_data.get("title", "Unknown")

        # Store tvdb_id for the next callback
        context.user_data["pending_anime_tvdb_id"] = tvdb_id

        # Create monitoring options keyboard
        keyboard = []
        for monitor_type in MONITOR_ORDER:
            label = MONITOR_OPTIONS[monitor_type]
            keyboard.append([InlineKeyboardButton(label, callback_data=f"monitor_anime_{monitor_type}:{tvdb_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"Select monitoring type for '{title}':",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in button_add_anime: {e}")
        try:
            await query.answer("❌ An error occurred.", show_alert=True)
        except Exception as inner_e:
            logger.error(f"Failed to send error to user: {inner_e}")


async def button_monitor_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle anime monitoring option selection and add series."""
    await _add_from_monitor_callback(update, context, anime=True)


async def _inline_search_series(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    """Shared inline series search; strips the routing prefix (e.g. 'show', 'anime')."""
    raw = update.inline_query.query if update.inline_query else ""
    if not raw:
        return

    # Check if user is allowed
    if not is_authorized(update, context):
        return

    # Drop the leading routing keyword that got us here (length-based, case-insensitive)
    search_query = raw[len(prefix):].strip()
    if len(search_query) < 2:
        return

    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        return

    try:
        shows = await client.search_series(search_query)

        results = []
        for show in shows[:5]:
            tvdb_id = show.get("tvdbId", show.get("id"))
            title = show.get("title", "Unknown")
            year = show.get("year", "N/A")
            overview = show.get("overview", "")

            # The follow-up callback reads the title from here, same as /show and /anime.
            context.user_data[f"{prefix}_{tvdb_id}"] = {
                "title": title,
                "tvdb_id": tvdb_id,
                "year": year,
                "overview": overview,
            }

            emoji = "🎌" if prefix == "anime" else "📺"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"➕ Add {prefix.capitalize()}", callback_data=f"select_{prefix}:{tvdb_id}")]]
            )
            text = f"{emoji} <b>{title}</b> ({year})"
            if overview:
                text += f"\n\n{overview[:200]}"

            results.append(
                InlineQueryResultArticle(
                    id=f"{prefix}_{tvdb_id}",
                    title=f"{title} ({year})",
                    description=overview[:100] if overview else f"Add this {prefix} to Sonarr",
                    input_message_content=InputTextMessageContent(text, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
            )

        await update.inline_query.answer(results, cache_time=300)

    except Exception as e:
        logger.error(f"Error in inline query: {e}")


async def inline_query_sonarr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for shows (@bot show <title>)."""
    await _inline_search_series(update, context, "show")


async def inline_query_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for anime (@bot anime <title>)."""
    await _inline_search_series(update, context, "anime")

