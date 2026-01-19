import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from app.clients.sonarr import SonarrClient

logger = logging.getLogger(__name__)


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /show command to search and add TV shows to Sonarr."""
    if not update.message:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    # Check if a query was provided
    if not context.args:
        await update.message.reply_text(
            "📺 TV Show search\n\n"
            "Usage: /show <show title>\n"
            "Example: /show Breaking Bad"
        )
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching for: {query}")
    
    sonarr: SonarrClient = context.bot_data.get("sonarr_client")
    if not sonarr:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return
    
    results = await sonarr.search_series(query)
    
    if not results:
        await update.message.reply_text(f"❌ No TV shows found for: {query}")
        return
    
    # Create inline buttons for search results
    keyboard = []
    for idx, show in enumerate(results[:10], 1):  # Show up to 10 results
        title = show.get("title", "Unknown")
        year = show.get("year", "N/A")
        tvdb_id = show.get("tvdbId", "N/A")
        
        # Create button with show title and year
        button_text = f"📺 {title} ({year})"
        callback_data = json.dumps({"action": "add_show", "tvdb_id": tvdb_id, "title": title})
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Show search results
    response = f"📺 Found {len(results)} TV shows for: {query}\n\nClick a show to add it:"
    await update.message.reply_text(response, reply_markup=reply_markup)


async def add_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addshow command to add a TV show to Sonarr."""
    if not update.message:
        return
    
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📺 Add TV Show\n\n"
            "Usage: /addshow <show title>\n"
            "Example: /addshow Breaking Bad"
        )
        return
    
    query = " ".join(context.args)
    sonarr: SonarrClient = context.bot_data.get("sonarr_client")
    
    if not sonarr:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return
    
    results = await sonarr.search_series(query)
    
    if not results:
        await update.message.reply_text(f"❌ No TV shows found for: {query}")
        return
    
    # Add the first result
    show = results[0]
    title = show.get("title", "Unknown")
    tvdb_id = show.get("tvdbId")
    
    result = await sonarr.add_series(tvdb_id)
    
    if result:
        await update.message.reply_text(f"✅ Added '{title}' to Sonarr!")
    else:
        await update.message.reply_text(f"❌ Failed to add '{title}' to Sonarr.")


async def button_add_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button click to add TV show."""
    query = update.callback_query
    
    if not query or not query.data:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return
    
    try:
        callback_data = json.loads(query.data)
        action = callback_data.get("action")
        
        if action not in ("add_show", "add_anime"):
            return
        
        tvdb_id = callback_data.get("tvdb_id")
        title = callback_data.get("title", "Unknown")
        folder_path = callback_data.get("folder_path", "/tv")
        
        await query.answer("⏳ Adding...")
        
        sonarr: SonarrClient = context.bot_data.get("sonarr_client")
        if not sonarr:
            await query.answer("❌ Sonarr client not initialized.", show_alert=True)
            return
        
        result = await sonarr.add_series(tvdb_id, root_folder_path=folder_path)
        
        if result:
            folder_label = "Anime" if action == "add_anime" else "Shows"
            await query.edit_message_text(f"✅ Successfully added '{title}' to {folder_label}!")
        else:
            await query.answer(f"❌ Failed to add '{title}' to Sonarr.", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error adding show from button: {e}")
        await query.answer("❌ An error occurred while adding the show.", show_alert=True)


async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /anime command to search and add anime to Sonarr."""
    if not update.message:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    # Check if a query was provided
    if not context.args:
        await update.message.reply_text(
            "🎌 Anime search\n\n"
            "Usage: /anime <anime title>\n"
            "Example: /anime Demon Slayer"
        )
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching for: {query}")
    
    sonarr: SonarrClient = context.bot_data.get("sonarr_client")
    if not sonarr:
        await update.message.reply_text("❌ Sonarr client not initialized.")
        return
    
    results = await sonarr.search_series(query)
    
    if not results:
        await update.message.reply_text(f"❌ No anime found for: {query}")
        return
    
    # Create inline buttons for search results
    keyboard = []
    for idx, show in enumerate(results[:10], 1):  # Show up to 10 results
        title = show.get("title", "Unknown")
        year = show.get("year", "N/A")
        tvdb_id = show.get("tvdbId", "N/A")
        
        # Create button with anime title and year
        button_text = f"🎌 {title} ({year})"
        callback_data = json.dumps({"action": "add_anime", "tvdb_id": tvdb_id, "title": title, "folder_path": "/anime"})
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Show search results
    response = f"🎌 Found {len(results)} anime for: {query}\n\nClick an anime to add it:"
    await update.message.reply_text(response, reply_markup=reply_markup)


async def inline_query_sonarr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline query for TV shows (e.g., @botname show Breaking Bad)."""
    query = update.inline_query
    
    if not query or not query.query:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        return
    
    search_query = query.query.strip()
    
    # Check for 'show' prefix
    if not search_query.lower().startswith("show "):
        return
    
    # Remove 'show ' prefix
    search_query = search_query[5:].strip()
    
    if len(search_query) < 2:
        return
    
    sonarr: SonarrClient = context.bot_data.get("sonarr_client")
    if not sonarr:
        return
    
    try:
        results = await sonarr.search_series(search_query)
        
        if not results:
            return
        
        inline_results = []
        for idx, show in enumerate(results[:10]):
            title = show.get("title", "Unknown")
            year = show.get("year", "N/A")
            tvdb_id = show.get("tvdbId", "N/A")
            overview = show.get("overview", "")[:200]
            
            # Create button to add show
            button_data = json.dumps({"action": "add_show", "tvdb_id": tvdb_id, "title": title, "folder_path": "/tv"})
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Show", callback_data=button_data)]])
            
            # Format result text
            result_text = f"📺 <b>{title}</b> ({year})\n"
            if overview:
                result_text += f"\n{overview}"
            
            inline_results.append(
                InlineQueryResultArticle(
                    id=f"show_{tvdb_id}_{idx}",
                    title=f"{title} ({year})",
                    description=overview[:100] if overview else "Add this show to Sonarr",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                    thumbnail_url="https://img.icons8.com/external-others-biso-biso/256/external-tv-entertainment-media-others-biso-biso.png"
                )
            )
        
        await query.answer(inline_results, cache_time=300)
    
    except Exception as e:
        logger.error(f"Error in inline show query: {e}")


async def inline_query_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline query for anime (e.g., @botname anime Demon Slayer)."""
    query = update.inline_query
    
    if not query or not query.query:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        return
    
    search_query = query.query.strip()
    
    # Check for 'anime' prefix
    if not search_query.lower().startswith("anime "):
        return
    
    # Remove 'anime ' prefix
    search_query = search_query[6:].strip()
    
    if len(search_query) < 2:
        return
    
    sonarr: SonarrClient = context.bot_data.get("sonarr_client")
    if not sonarr:
        return
    
    try:
        results = await sonarr.search_series(search_query)
        
        if not results:
            return
        
        inline_results = []
        for idx, show in enumerate(results[:10]):
            title = show.get("title", "Unknown")
            year = show.get("year", "N/A")
            tvdb_id = show.get("tvdbId", "N/A")
            overview = show.get("overview", "")[:200]
            
            # Create button to add anime
            button_data = json.dumps({"action": "add_anime", "tvdb_id": tvdb_id, "title": title, "folder_path": "/anime"})
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Anime", callback_data=button_data)]])
            
            # Format result text
            result_text = f"🎌 <b>{title}</b> ({year})\n"
            if overview:
                result_text += f"\n{overview}"
            
            inline_results.append(
                InlineQueryResultArticle(
                    id=f"anime_{tvdb_id}_{idx}",
                    title=f"{title} ({year})",
                    description=overview[:100] if overview else "Add this anime to Sonarr",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                    thumbnail_url="https://img.icons8.com/external-others-biso-biso/256/external-tv-entertainment-media-others-biso-biso.png"
                )
            )
        
        await query.answer(inline_results, cache_time=300)
    
    except Exception as e:
        logger.error(f"Error in inline anime query: {e}")


def _is_user_allowed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is in allowed list."""
    allowed_users = context.bot_data.get("allowed_users", [])
    return user_id in allowed_users

