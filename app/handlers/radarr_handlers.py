import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from app.clients.radarr import RadarrClient
from app.config.settings import settings
from app.handlers.general_handlers import find_in_library, format_size, is_authorized, reply_in_chunks, safe_edit
from app.handlers.prompts import send_search_prompt

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
    
    # Tapped from the "/" list rather than typed with a title — ask for one
    # instead of printing usage at someone who just pressed a button.
    if not context.args:
        logger.info("movie_command: no arguments, prompting for a title")
        await send_search_prompt(update, "movie")
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

        # Lookup results already in the library carry their Radarr id. Adding
        # those again would only fail, so open the manage panel instead.
        if movie.get("id"):
            keyboard.append([InlineKeyboardButton(f"⚙️ {title} ({year}) · in library",
                                                  callback_data=f"mv:view:{movie['id']}")])
            continue

        # Stashed for the callback, which only carries the id.
        context.user_data[f"movie_{tmdb_id}"] = {
            "tmdb_id": tmdb_id, "title": title, "folder_path": settings.radarr_root_movies
        }

        keyboard.append([InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=f"add_movie:{tmdb_id}")])

    response = f"🎬 Found {len(results)} movies for: {query}\n\nTap a movie to add it (⚙️ = already in the library, tap to manage):"
    await message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))


async def add_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addmovie command to add a movie to Radarr."""
    if not update.message:
        return
    
    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    
    if not context.args:
        await send_search_prompt(update, "addmovie")
        return

    await add_top_movie_and_reply(update, context, " ".join(context.args))


async def add_top_movie_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Add the best match for a title outright, skipping the picker.

    Shared by /addmovie and its ForceReply prompt, so it replies to
    effective_message rather than assuming the update carries a command.
    """
    message = update.effective_message
    radarr: RadarrClient = context.bot_data.get("radarr_client")

    if not radarr:
        await message.reply_text("❌ Radarr client not initialized.")
        return

    results = await radarr.search_movies(query)

    if not results:
        await message.reply_text(f"❌ No movies found for: {query}")
        return

    # Add the first result
    movie = results[0]
    title = movie.get("title", "Unknown")
    tmdb_id = movie.get("tmdbId")

    if movie.get("id"):
        text, keyboard = movie_panel(movie)
        await message.reply_text(f"ℹ️ Already in the library.\n\n{text}", reply_markup=keyboard)
        return

    result = await radarr.add_movie(tmdb_id, root_folder_path=settings.radarr_root_movies)

    if result:
        # Radarr searches for this movie on add via addOptions.searchForMovie — no library-wide search.
        await message.reply_text(f"✅ Added '{title}' to Radarr and started searching for it!")
    else:
        await message.reply_text(f"❌ Failed to add '{title}' to Radarr.")


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
            # Radarr searches for this movie on add via addOptions.searchForMovie — no library-wide search.
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
            
            # Already in the library -> manage it; otherwise offer to add it.
            if movie.get("id"):
                button = InlineKeyboardButton("⚙️ Manage", callback_data=f"mv:view:{movie['id']}")
            else:
                button = InlineKeyboardButton("➕ Add Movie", callback_data=f"add_movie:{tmdb_id}")
            keyboard = InlineKeyboardMarkup([[button]])
            
            # Format result text
            result_text = f"📽️ <b>{title}</b> ({year})\n"
            if overview:
                result_text += f"\n{overview}"
            
            inline_results.append(
                InlineQueryResultArticle(
                    id=f"movie_{tmdb_id}_{idx}",
                    title=f"{title} ({year})",
                    description=("✅ In library · " if movie.get("id") else "") + (overview[:100] if overview else "Add this movie to Radarr"),
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                    thumbnail_url="https://img.icons8.com/external-others-biso-biso/256/external-movie-entertainment-media-others-biso-biso.png"
                )
            )
        
        await query.answer(inline_results, cache_time=300)
    
    except Exception as e:
        logger.error(f"Error in inline movie query: {e}")



# --- Library management -----------------------------------------------------
#
# Buttons carry mv:<action>:<radarr id>. That's Radarr's own id rather than the
# TMDb one, and nothing is stashed in user_data, so a panel keeps working after
# a restart and for anyone else in the group who taps it.

def _movie_label(movie: dict) -> str:
    return f"{movie.get('title', 'Unknown')} ({movie.get('year', 'N/A')})"


def _movie_size(movie: dict) -> int:
    # Radarr v5 moved sizeOnDisk under statistics; older versions have it top-level.
    return movie.get("sizeOnDisk") or (movie.get("statistics") or {}).get("sizeOnDisk") or 0


def movie_panel(movie: dict) -> tuple[str, InlineKeyboardMarkup]:
    """The manage view for one library movie."""
    movie_id = movie["id"]
    monitored = movie.get("monitored", False)

    lines = [
        f"🎬 {_movie_label(movie)}",
        f"Monitored: {'✅ yes' if monitored else '🚫 no'}",
    ]
    if movie.get("hasFile"):
        lines.append(f"File: ✅ downloaded ({format_size(_movie_size(movie))})")
    else:
        lines.append("File: ⏳ not downloaded yet")

    toggle = (InlineKeyboardButton("🚫 Unmonitor", callback_data=f"mv:unmon:{movie_id}") if monitored
              else InlineKeyboardButton("👁️ Monitor", callback_data=f"mv:mon:{movie_id}"))
    keyboard = InlineKeyboardMarkup([
        [toggle, InlineKeyboardButton("🔍 Search now", callback_data=f"mv:search:{movie_id}")],
        [InlineKeyboardButton("🗑️ Remove", callback_data=f"mv:rm:{movie_id}")],
    ])
    return "\n".join(lines), keyboard


def _movie_remove_confirm(movie: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Ask what Radarr's delete dialog asks: drop the entry, or the files on disk too."""
    movie_id = movie["id"]
    lines = [f"🗑️ Remove {_movie_label(movie)} from Radarr?", ""]
    if movie.get("path"):
        lines.append(f"📁 {movie['path']}")
    if movie.get("hasFile"):
        lines.append(f"💾 {format_size(_movie_size(movie))} on disk")
    else:
        lines.append("💾 Nothing downloaded yet")
    lines += ["", "Also delete the downloaded files from the drive?"]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Remove, keep files", callback_data=f"mv:rmk:{movie_id}")],
        [InlineKeyboardButton("💥 Remove and delete files", callback_data=f"mv:rmd:{movie_id}")],
        [InlineKeyboardButton("↩️ Cancel", callback_data=f"mv:view:{movie_id}")],
    ])
    return "\n".join(lines), keyboard


async def manage_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /managemovie <title> — find a library movie and open its manage panel."""
    if not update.message:
        return

    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        await send_search_prompt(update, "managemovie")
        return

    await manage_movie_and_reply(update, context, " ".join(context.args))


async def manage_movie_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Look a title up in the Radarr library (not TMDb) and offer the matches.

    Shared by /managemovie and its ForceReply prompt.
    """
    message = update.effective_message
    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await message.reply_text("❌ Radarr client not initialized.")
        return

    matches = find_in_library(await radarr.get_monitored_movies(), query)

    if not matches:
        await message.reply_text(f"❌ No movie matching '{query}' in the library. Use /movie to add one.")
        return

    if len(matches) == 1:
        text, keyboard = movie_panel(matches[0])
        await message.reply_text(text, reply_markup=keyboard)
        return

    keyboard = [[InlineKeyboardButton(f"🎬 {_movie_label(m)}", callback_data=f"mv:view:{m['id']}")]
                for m in matches]
    await message.reply_text("Which movie?", reply_markup=InlineKeyboardMarkup(keyboard))


async def button_manage_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the manage panel buttons: mv:<view|mon|unmon|search|rm|rmk|rmd>:<radarr id>."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        _, action, raw_id = query.data.split(":", 2)
        movie_id = int(raw_id)
    except ValueError:
        await query.answer("❌ Invalid button data.", show_alert=True)
        return

    radarr: RadarrClient = context.bot_data.get("radarr_client")
    if not radarr:
        await query.answer("❌ Radarr client not initialized.", show_alert=True)
        return

    try:
        # Always re-read: the panel may be hours old, or edited in Radarr since.
        movie = await radarr.get_movie(movie_id)
        if not movie:
            await query.answer()
            await safe_edit(query, "❌ That movie is no longer in the Radarr library.")
            return

        title = _movie_label(movie)
        toast = None

        if action in ("mon", "unmon"):
            movie["monitored"] = action == "mon"
            updated = await radarr.update_movie(movie)
            if not updated:
                await query.answer(f"❌ Couldn't update {title}.", show_alert=True)
                return
            movie = updated
            toast = "👁️ Monitored" if action == "mon" else "🚫 Unmonitored"
            logger.info(f"user {update.effective_user.id} set movie {movie_id} monitored={movie['monitored']}")

        elif action == "search":
            if not await radarr.trigger_movie_search(movie_id):
                await query.answer("❌ Couldn't start the search.", show_alert=True)
                return
            toast = f"🔍 Searching for {title}"

        elif action == "rm":
            await query.answer()
            text, keyboard = _movie_remove_confirm(movie)
            await safe_edit(query, text, keyboard)
            return

        elif action in ("rmk", "rmd"):
            delete_files = action == "rmd"
            await query.answer("⏳ Removing...")
            if not await radarr.delete_movie(movie_id, delete_files=delete_files):
                await safe_edit(query, f"❌ Failed to remove {title} from Radarr.")
                return
            logger.info(f"user {update.effective_user.id} removed movie {movie_id} ({title}), deleteFiles={delete_files}")
            suffix = "and deleted its files from the drive" if delete_files else "— files left on the drive"
            await safe_edit(query, f"🗑️ Removed {title} from Radarr {suffix}.")
            return

        elif action != "view":
            await query.answer("❌ Unknown option.", show_alert=True)
            return

        await query.answer(toast)
        text, keyboard = movie_panel(movie)
        await safe_edit(query, text, keyboard)

    except Exception as e:
        logger.error(f"Error in button_manage_movie ({query.data}): {e}")
        try:
            await query.answer("❌ An error occurred.", show_alert=True)
        except Exception:
            pass
