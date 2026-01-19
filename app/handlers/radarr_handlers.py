import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from app.clients.radarr import RadarrClient

logger = logging.getLogger(__name__)


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /movie command to search and add movies to Radarr."""
    if not update.message:
        return
    
    # Check if user is allowed
    if not _is_user_allowed(update.effective_user.id, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    # Check if a query was provided
    if not context.args:
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
    
    # Show top 5 results
    response = "🎬 Found movies:\n\n"
    for idx, movie in enumerate(results[:5], 1):
        title = movie.get("title", "Unknown")
        year = movie.get("year", "N/A")
        tmdb_id = movie.get("tmdbId", "N/A")
        overview = movie.get("overview", "")[:100]
        
        response += f"{idx}. **{title}** ({year})\n"
        response += f"   ID: `{tmdb_id}`\n"
        if overview:
            response += f"   {overview}...\n"
        response += "\n"
    
    response += "Use `/addmovie <title>` to add a movie."
    await update.message.reply_text(response, parse_mode="Markdown")


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
    
    result = await radarr.add_movie(tmdb_id)
    
    if result:
        await update.message.reply_text(f"✅ Added '{title}' to Radarr!")
    else:
        await update.message.reply_text(f"❌ Failed to add '{title}' to Radarr.")


def _is_user_allowed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is in allowed list."""
    allowed_users = context.bot_data.get("allowed_users", [])
    return user_id in allowed_users
