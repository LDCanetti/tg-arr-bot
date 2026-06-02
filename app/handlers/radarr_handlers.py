import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from app.clients.radarr import RadarrClient
from app.config.settings import settings
from app.handlers.general_handlers import reply_in_chunks

logger = logging.getLogger(__name__)


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /movie command to search and add movies to Radarr."""
    logger.info(f"movie_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"movie_command: No message in update")
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        logger.warning(f"movie_command: User {update.effective_user.id} not in allowed users")
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    # Check if a query was provided
    if not context.args:
        logger.info(f"movie_command: No arguments provided")
        await update.message.reply_text(
            "🎬 Movie search\n\n"
            "Usage: /movie <movie title>\n"
            "Example: /movie The Matrix"
        )
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching for: {query}")
    
    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await update.message.reply_text("❌ Radarr client not initialized.")
        return
    
    results = await radarr.search_movies(query)
    
    if not results:
        await update.message.reply_text(f"❌ No movies found for: {query}")
        return
    
    # Store results in context for button callbacks
    if not hasattr(context, 'user_data'):
        context.user_data = {}
    
    # Create inline buttons for search results
    keyboard = []
    for idx, movie in enumerate(results[:10], 1):  # Show up to 10 results
        title = movie.get("title", "Unknown")
        year = movie.get("year", "N/A")
        tmdb_id = movie.get("tmdbId", "N/A")
        
        # Store movie data with a unique key
        data_key = f"movie_{tmdb_id}"
        context.user_data[data_key] = {"tmdb_id": tmdb_id, "title": title, "folder_path": settings.radarr_root_movies}
        
        # Create button with movie title and year - just store the tmdb_id as callback data
        button_text = f"📽️ {title} ({year})"
        callback_data = f"add_movie:{tmdb_id}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Show search results
    response = f"🎬 Found {len(results)} movies for: {query}\n\nClick a movie to add it:"
    await update.message.reply_text(response, reply_markup=reply_markup)


async def add_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addmovie command to add a movie to Radarr."""
    if not update.message:
        return
    
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🎬 Add Movie\n\n"
            "Usage: /addmovie <movie title>\n"
            "Example: /addmovie The Matrix"
        )
        return
    
    query = " ".join(context.args)
    radarr: RadarrClient = context.bot_data.get("radarr_client")
    
    if not radarr:
        await update.message.reply_text("❌ Radarr client not initialized.")
        return
    
    results = await radarr.search_movies(query)
    
    if not results:
        await update.message.reply_text(f"❌ No movies found for: {query}")
        return
    
    # Add the first result
    movie = results[0]
    title = movie.get("title", "Unknown")
    tmdb_id = movie.get("tmdbId")
    
    result = await radarr.add_movie(tmdb_id, root_folder_path=settings.radarr_root_movies)
    
    if result:
        # Trigger search for all monitored movies
        search_success = await radarr.trigger_monitored_search()
        if search_success:
            await update.message.reply_text(f"✅ Added '{title}' to Radarr and started searching monitored movies!")
        else:
            await update.message.reply_text(f"✅ Added '{title}' to Radarr (search trigger failed)")
    else:
        await update.message.reply_text(f"❌ Failed to add '{title}' to Radarr.")


async def my_movies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mymovies command to list movies in the Radarr library."""
    logger.info(f"my_movies_command called from user {update.effective_user.id}")
    if not update.message:
        return

    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await update.message.reply_text("❌ Radarr client not initialized.")
        return

    movies = await radarr.get_monitored_movies()
    if not movies:
        await update.message.reply_text("🎬 No movies in your Radarr library yet.")
        return

    movies.sort(key=lambda m: (m.get("sortTitle") or m.get("title") or "").lower())
    lines = [
        f"{'✅' if m.get('hasFile') else '⏳'} {m.get('title', 'Unknown')} ({m.get('year', 'N/A')})"
        for m in movies
    ]
    await reply_in_chunks(update.message, f"🎬 Your movies ({len(movies)}):\n", lines)


async def button_add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button click to add movie."""
    query = update.callback_query
    
    if not query:
        return
    
    if not query.data:
        logger.warning("Received callback query without data")
        await query.answer("❌ Invalid button data.", show_alert=True)
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return
    
    try:
        # Parse callback data: "add_movie:tmdb_id"
        if not query.data.startswith("add_movie:"):
            return
        
        tmdb_id = query.data.split(":", 1)[1]
        
        # Get title and folder path from stored data
        data_key = f"movie_{tmdb_id}"
        movie_data = context.user_data.get(data_key, {}) if context.user_data else {}
        title = movie_data.get("title", "Unknown")
        folder_path = movie_data.get("folder_path", settings.radarr_root_movies)
        
        # Acknowledge button press
        await query.answer("⏳ Adding movie...")
        
        radarr: RadarrClient = context.bot_data.get("radarr_client")
        if not radarr:
            await query.answer("❌ Radarr client not initialized.", show_alert=True)
            return
        
        result = await radarr.add_movie(tmdb_id, root_folder_path=folder_path)
        
        if result:
            # Trigger search for all monitored movies
            search_success = await radarr.trigger_monitored_search()
            if search_success:
                await query.edit_message_text(f"✅ Successfully added '{title}' to Radarr and started searching monitored movies!")
            else:
                await query.edit_message_text(f"✅ Successfully added '{title}' to Radarr (search trigger failed)")
        else:
            await query.answer(f"❌ Failed to add '{title}' to Radarr.", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error adding movie from button: {e}")
        await query.answer("❌ An error occurred while adding the movie.", show_alert=True)


def _is_user_allowed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is in allowed list."""
    allowed_users = context.bot_data.get("allowed_users", [])
    return user_id in allowed_users


async def inline_query_radarr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline query for movies (e.g., @botname movie The Matrix)."""
    query = update.inline_query
    
    if not query or not query.query:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        return
    
    search_query = query.query.strip()
    
    # Check for 'movie' prefix
    if not search_query.lower().startswith("movie "):
        return
    
    # Remove 'movie ' prefix
    search_query = search_query[6:].strip()
    
    if len(search_query) < 2:
        return
    
    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        return
    
    try:
        results = await radarr.search_movies(search_query)
        
        if not results:
            return
        
        inline_results = []
        for idx, movie in enumerate(results[:10]):
            title = movie.get("title", "Unknown")
            year = movie.get("year", "N/A")
            tmdb_id = movie.get("tmdbId", "N/A")
            overview = movie.get("overview", "")[:200]
            
            # Store movie data in context for later retrieval (avoid JSON in callback_data)
            data_key = f"inline_movie_{tmdb_id}"
            context.user_data[data_key] = {"tmdb_id": tmdb_id, "title": title}
            
            # Create button to add movie with simple callback_data format
            callback_data = f"add_movie:{tmdb_id}"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Movie", callback_data=callback_data)]])
            
            # Format result text
            result_text = f"📽️ <b>{title}</b> ({year})\n"
            if overview:
                result_text += f"\n{overview}"
            
            inline_results.append(
                InlineQueryResultArticle(
                    id=f"movie_{tmdb_id}_{idx}",
                    title=f"{title} ({year})",
                    description=overview[:100] if overview else "Add this movie to Radarr",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                    thumbnail_url="https://img.icons8.com/external-others-biso-biso/256/external-movie-entertainment-media-others-biso-biso.png"
                )
            )
        
        await query.answer(inline_results, cache_time=300)
    
    except Exception as e:
        logger.error(f"Error in inline movie query: {e}")

