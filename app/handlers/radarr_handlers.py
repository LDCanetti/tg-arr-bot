import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from app.clients.radarr import RadarrClient
from app.config.settings import settings
from app.handlers.general_handlers import is_authorized, reply_in_chunks

logger = logging.getLogger(__name__)


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /movie command to search and add movies to Radarr."""
    logger.info(f"movie_command called from user {update.effective_user.id}")
    if not update.message:
        logger.warning(f"movie_command: No message in update")
        return
    
    # Check if user is allowed
    if not is_authorized(update, context):
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
    
    await search_movies_and_reply(update, context, " ".join(context.args))


async def search_movies_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Search Radarr and offer the hits as buttons.

    Shared by /movie and the tap-to-search menu, so it replies to
    effective_message rather than assuming the update carries a command.
    """
    message = update.effective_message
    await message.reply_text(f"🔍 Searching for: {query}")

    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await message.reply_text("❌ Radarr client not initialized.")
        return

    results = await radarr.search_movies(query)

    if not results:
        await message.reply_text(f"❌ No movies found for: {query}")
        return

    # Create inline buttons for search results
    keyboard = []
    for movie in results[:10]:  # Show up to 10 results
        title = movie.get("title", "Unknown")
        year = movie.get("year", "N/A")
        tmdb_id = movie.get("tmdbId", "N/A")

        # Stashed for the callback, which only carries the id.
        context.user_data[f"movie_{tmdb_id}"] = {
            "tmdb_id": tmdb_id, "title": title, "folder_path": settings.radarr_root_movies
        }

        keyboard.append([InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=f"add_movie:{tmdb_id}")])

    response = f"🎬 Found {len(results)} movies for: {query}\n\nClick a movie to add it:"
    await message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))


async def add_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addmovie command to add a movie to Radarr."""
    if not update.message:
        return
    
    if not is_authorized(update, context):
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
        # Radarr searches for this movie on add via searchForMovie — no library-wide search.
        await update.message.reply_text(f"✅ Added '{title}' to Radarr and started searching for it!")
    else:
        await update.message.reply_text(f"❌ Failed to add '{title}' to Radarr.")


async def my_movies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List movies in the Radarr library; used by /mymovies and the Library menu."""
    logger.info(f"my_movies_command called from user {update.effective_user.id}")
    message = update.effective_message
    if not message:
        return

    if not is_authorized(update, context):
        await message.reply_text("❌ You don't have permission to use this bot.")
        return

    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await message.reply_text("❌ Radarr client not initialized.")
        return

    movies = await radarr.get_monitored_movies()
    if not movies:
        await message.reply_text("🎬 No movies in your Radarr library yet.")
        return

    movies.sort(key=lambda m: (m.get("sortTitle") or m.get("title") or "").lower())
    lines = [
        f"{'✅' if m.get('hasFile') else '⏳'} {m.get('title', 'Unknown')} ({m.get('year', 'N/A')})"
        for m in movies
    ]
    await reply_in_chunks(message, f"🎬 Your movies ({len(movies)}):\n", lines)


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
    if not is_authorized(update, context):
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
            # Radarr searches for this movie on add via searchForMovie — no library-wide search.
            await query.edit_message_text(f"✅ Successfully added '{title}' to Radarr and started searching for it!")
        else:
            await query.answer(f"❌ Failed to add '{title}' to Radarr.", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error adding movie from button: {e}")
        await query.answer("❌ An error occurred while adding the movie.", show_alert=True)


async def inline_query_radarr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline query for movies (e.g., @botname movie The Matrix)."""
    query = update.inline_query
    
    if not query or not query.query:
        return
    
    # Check if user is allowed
    if not is_authorized(update, context):
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

