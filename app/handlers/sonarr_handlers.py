import logging
from telegram import Update
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
    
    # Show top 5 results
    response = "📺 Found TV shows:\n\n"
    for idx, show in enumerate(results[:5], 1):
        title = show.get("title", "Unknown")
        year = show.get("year", "N/A")
        tvdb_id = show.get("tvdbId", "N/A")
        overview = show.get("overview", "")[:100]
        
        response += f"{idx}. **{title}** ({year})\n"
        response += f"   ID: `{tvdb_id}`\n"
        if overview:
            response += f"   {overview}...\n"
        response += "\n"
    
    response += "Use `/addshow <title>` to add a show."
    await update.message.reply_text(response, parse_mode="Markdown")


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


def _is_user_allowed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is in allowed list."""
    allowed_users = context.bot_data.get("allowed_users", [])
    return user_id in allowed_users
