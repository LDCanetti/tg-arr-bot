import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.clients.sonarr import SonarrClient

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


def _is_user_allowed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is allowed to use admin commands."""
    allowed_users = context.bot_data.get("allowed_users", [])
    return user_id in allowed_users


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /show command to search for TV shows."""
    if not update.message:
        return
    
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
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


async def button_monitor_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle show monitoring option selection and add series."""
    query = update.callback_query
    
    if not query or not query.data:
        logger.warning("Received callback query without data in button_monitor_show")
        return
    
    try:
        await query.answer()
        
        # Parse callback data: monitor_show_<type>:<tvdb_id>
        parts = query.data.split(":")
        tvdb_id = int(parts[1])
        monitor_type = query.data.split("_", 2)[2].split(":")[0]  # Extract monitor type
        
        data_key = f"show_{tvdb_id}"
        show_data = context.user_data.get(data_key, {})
        title = show_data.get("title", "Unknown")
        
        client: SonarrClient = context.bot_data.get("sonarr_client")
        
        if not client:
            await query.answer("❌ Sonarr client not initialized.", show_alert=True)
            return
        
        result = await client.add_series(
            series_id=tvdb_id,
            title=title,
            root_folder_path="/Shows",
            quality_profile_id=1,
            monitor_seasons=monitor_type
        )
        
        if result:
            # Trigger immediate search
            search_success = await client.trigger_series_search(result.get("id"))
            monitor_label = MONITOR_OPTIONS.get(monitor_type, monitor_type)
            if search_success:
                await query.edit_message_text(
                    text=f"✅ Show '{title}' added with monitoring: {monitor_label}\n🔍 Started searching!"
                )
            else:
                await query.edit_message_text(
                    text=f"✅ Show '{title}' added with monitoring: {monitor_label}\n⚠️ Search trigger failed"
                )
        else:
            monitor_label = MONITOR_OPTIONS.get(monitor_type, monitor_type)
            await query.edit_message_text(text=f"❌ Error adding show")
        
    except Exception as e:
        logger.error(f"Error adding show: {e}")
        try:
            await query.edit_message_text(text=f"❌ Error adding show: {str(e)}")
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")


async def add_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addshow command."""
    await show_command(update, context)


async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /anime command to search for anime."""
    if not update.message:
        return
    
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
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
    query = update.callback_query
    
    if not query or not query.data:
        logger.warning("Received callback query without data in button_monitor_anime")
        return
    
    try:
        await query.answer()
        
        # Parse callback data: monitor_anime_<type>:<tvdb_id>
        parts = query.data.split(":")
        tvdb_id = int(parts[1])
        monitor_type = query.data.split("_", 2)[2].split(":")[0]  # Extract monitor type
        
        data_key = f"anime_{tvdb_id}"
        anime_data = context.user_data.get(data_key, {})
        title = anime_data.get("title", "Unknown")
        
        client: SonarrClient = context.bot_data.get("sonarr_client")
        
        if not client:
            await query.answer("❌ Sonarr client not initialized.", show_alert=True)
            return
        
        result = await client.add_series(
            series_id=tvdb_id,
            title=title,
            root_folder_path="/Anime",
            quality_profile_id=1,
            monitor_seasons=monitor_type
        )
        
        if result:
            # Trigger immediate search
            search_success = await client.trigger_series_search(result.get("id"))
            monitor_label = MONITOR_OPTIONS.get(monitor_type, monitor_type)
            if search_success:
                await query.edit_message_text(
                    text=f"✅ Anime '{title}' added with monitoring: {monitor_label}\n🔍 Started searching!"
                )
            else:
                await query.edit_message_text(
                    text=f"✅ Anime '{title}' added with monitoring: {monitor_label}\n⚠️ Search trigger failed"
                )
        else:
            monitor_label = MONITOR_OPTIONS.get(monitor_type, monitor_type)
            await query.edit_message_text(text=f"❌ Error adding anime")
        
    except Exception as e:
        logger.error(f"Error adding anime: {e}")
        try:
            await query.edit_message_text(text=f"❌ Error adding anime: {str(e)}")
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")


async def inline_query_sonarr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for shows."""
    query = update.inline_query.query
    
    if not query:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        return
    
    client: SonarrClient = context.bot_data.get("sonarr_client")
    
    if not client:
        return
    
    try:
        shows = await client.search_series(query)
        
        from telegram import InlineQueryResultArticle, InputTextMessageContent
        
        results = []
        for show in shows[:5]:
            tvdb_id = show.get("tvdbId", show.get("id"))
            title = show.get("title", "Unknown")
            overview = show.get("overview", "")
            
            results.append(
                InlineQueryResultArticle(
                    id=str(tvdb_id),
                    title=title,
                    input_message_content=InputTextMessageContent(
                        message_text=f"Found: {title}"
                    ),
                    description=overview[:100]
                )
            )
        
        await update.inline_query.answer(results)
        
    except Exception as e:
        logger.error(f"Error in inline query: {e}")


async def inline_query_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for anime."""
    await inline_query_sonarr(update, context)

