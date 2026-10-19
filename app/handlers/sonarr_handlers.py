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
from app.handlers.general_handlers import find_in_library, format_size, is_authorized, reply_in_chunks, safe_edit
from app.handlers.prompts import send_search_prompt

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


async def search_series_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  query: str, anime: bool) -> None:
    """Search Sonarr and offer the hits as buttons.

    Shared by /show, /anime and the tap-to-search menu, so it replies to
    effective_message rather than assuming the update carries a command.
    """
    message = update.effective_message
    kind = "anime" if anime else "show"
    noun = "anime" if anime else "shows"

    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        await message.reply_text("❌ Sonarr client not initialized.")
        return

    try:
        results = await client.search_series(query)

        if not results:
            await message.reply_text(f"No {noun} found for '{query}'")
            return

        keyboard = []
        for item in results[:10]:  # Limit to 10 results
            tvdb_id = item.get("tvdbId", item.get("id"))
            title = item.get("title", "Unknown")
            year = item.get("year", "")
            label = f"{title} ({year})" if year else title

            # Lookup results already in the library carry their Sonarr id. Adding
            # those again would only fail, so open the manage panel instead.
            if item.get("id"):
                keyboard.append([InlineKeyboardButton(f"⚙️ {label} · in library",
                                                      callback_data=f"tv:view:{item['id']}")])
                continue

            # Stashed for the callback, which only carries the id.
            context.user_data[f"{kind}_{tvdb_id}"] = {
                "title": title,
                "tvdb_id": tvdb_id,
                "year": year,
                "overview": item.get("overview", ""),
            }

            keyboard.append([InlineKeyboardButton(label, callback_data=f"select_{kind}:{tvdb_id}")])

        await message.reply_text(
            f"Select {'an anime' if anime else 'a show'} (⚙️ = already in the library, tap to manage):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        logger.error(f"Error searching {noun}: {e}")
        await message.reply_text(f"Error searching {noun}: {str(e)}")


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /show command to search for TV shows."""
    logger.info(f"show_command called from user {update.effective_user.id}")
    if not update.message:
        return

    if not is_authorized(update, context):
        logger.warning(f"show_command: user {update.effective_user.id} not authorized")
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    # Tapped from the "/" list rather than typed with a title — ask for one
    # instead of printing usage at someone who just pressed a button.
    if not context.args:
        await send_search_prompt(update, "show")
        return

    await search_series_and_reply(update, context, " ".join(context.args), anime=False)


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


async def list_series(update: Update, context: ContextTypes.DEFAULT_TYPE, anime: bool) -> None:
    """Shared lister for /myshows, /myanime and the menu's Library buttons."""
    message = update.effective_message
    if not message:
        return

    if not is_authorized(update, context):
        await message.reply_text("❌ You don't have permission to use this bot.")
        return

    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        await message.reply_text("❌ Sonarr client not initialized.")
        return

    series = await client.get_monitored_series()
    filtered = [s for s in series if (s.get("seriesType", "").lower() == "anime") == anime]

    emoji = "🎌" if anime else "📺"
    label = "anime" if anime else "shows"
    if not filtered:
        await message.reply_text(f"{emoji} No {label} in your Sonarr library yet.")
        return

    filtered.sort(key=lambda s: (s.get("sortTitle") or s.get("title") or "").lower())
    lines = [
        f"{'✅' if s.get('statistics', {}).get('episodeFileCount', 0) else '⏳'} "
        f"{s.get('title', 'Unknown')} ({s.get('year', 'N/A')})"
        for s in filtered
    ]
    await reply_in_chunks(message, f"{emoji} Your {label} ({len(filtered)}):\n", lines)


async def my_shows_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /myshows command to list standard TV shows in Sonarr."""
    logger.info(f"my_shows_command called from user {update.effective_user.id}")
    await list_series(update, context, anime=False)


async def my_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /myanime command to list anime in Sonarr."""
    logger.info(f"my_anime_command called from user {update.effective_user.id}")
    await list_series(update, context, anime=True)


async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /anime command to search for anime."""
    logger.info(f"anime_command called from user {update.effective_user.id}")
    if not update.message:
        return

    if not is_authorized(update, context):
        logger.warning(f"anime_command: user {update.effective_user.id} not authorized")
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        await send_search_prompt(update, "anime")
        return

    await search_series_and_reply(update, context, " ".join(context.args), anime=True)


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
            # Already in the library -> manage it; otherwise offer to add it.
            if show.get("id"):
                button = InlineKeyboardButton("⚙️ Manage", callback_data=f"tv:view:{show['id']}")
            else:
                button = InlineKeyboardButton(f"➕ Add {prefix.capitalize()}", callback_data=f"select_{prefix}:{tvdb_id}")
            keyboard = InlineKeyboardMarkup([[button]])
            text = f"{emoji} <b>{title}</b> ({year})"
            if overview:
                text += f"\n\n{overview[:200]}"

            results.append(
                InlineQueryResultArticle(
                    id=f"{prefix}_{tvdb_id}",
                    title=f"{title} ({year})",
                    description=("✅ In library · " if show.get("id") else "") + (overview[:100] if overview else f"Add this {prefix} to Sonarr"),
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



# --- Library management -----------------------------------------------------
#
# Buttons carry tv:<action>:<sonarr id>[:<season>]. That's Sonarr's own id rather
# than the TVDB one, and nothing is stashed in user_data, so a panel keeps working
# after a restart and for anyone else in the group who taps it. Shows and anime
# share all of this; the only difference is the emoji.

def _series_label(series: dict) -> str:
    return f"{series.get('title', 'Unknown')} ({series.get('year', 'N/A')})"


def _series_emoji(series: dict) -> str:
    return "🎌" if (series.get("seriesType") or "").lower() == "anime" else "📺"


def _season_name(number: int) -> str:
    return "Specials" if number == 0 else f"Season {number}"


def series_panel(series: dict) -> tuple[str, InlineKeyboardMarkup]:
    """The manage view for one library series."""
    series_id = series["id"]
    monitored = series.get("monitored", False)
    stats = series.get("statistics") or {}
    # Specials don't count towards "x of y seasons", same as Sonarr's own UI.
    seasons = [s for s in series.get("seasons", []) if s.get("seasonNumber", 0) > 0]
    monitored_seasons = sum(1 for s in seasons if s.get("monitored"))

    lines = [
        f"{_series_emoji(series)} {_series_label(series)}",
        f"Monitored: {'✅ yes' if monitored else '🚫 no'}",
        f"Seasons monitored: {monitored_seasons} of {len(seasons)}",
        f"Episodes on disk: {stats.get('episodeFileCount', 0)} of {stats.get('episodeCount', 0)}"
        f" · {format_size(stats.get('sizeOnDisk', 0))}",
    ]
    if series.get("status"):
        lines.append(f"Status: {series['status']}")

    toggle = (InlineKeyboardButton("🚫 Unmonitor show", callback_data=f"tv:unmon:{series_id}") if monitored
              else InlineKeyboardButton("👁️ Monitor show", callback_data=f"tv:mon:{series_id}"))
    keyboard = InlineKeyboardMarkup([
        [toggle, InlineKeyboardButton("📂 Seasons", callback_data=f"tv:seasons:{series_id}")],
        [InlineKeyboardButton("🔍 Search monitored", callback_data=f"tv:search:{series_id}"),
         InlineKeyboardButton("🗑️ Remove", callback_data=f"tv:rm:{series_id}")],
    ])
    return "\n".join(lines), keyboard


def _seasons_panel(series: dict) -> tuple[str, InlineKeyboardMarkup]:
    """One toggle button per season, two to a row."""
    series_id = series["id"]
    seasons = sorted(series.get("seasons", []), key=lambda s: s.get("seasonNumber", 0))

    buttons = []
    for season in seasons:
        number = season.get("seasonNumber", 0)
        stats = season.get("statistics") or {}
        mark = "✅" if season.get("monitored") else "⬜"
        label = f"{mark} {_season_name(number)} · {stats.get('episodeFileCount', 0)}/{stats.get('totalEpisodeCount', 0)}"
        buttons.append(InlineKeyboardButton(label, callback_data=f"tv:st:{series_id}:{number}"))
    # Telegram allows 100 buttons per message; leave room for the footer rows.
    rows = [buttons[i:i + 2] for i in range(0, min(len(buttons), 90), 2)]
    rows += [
        [InlineKeyboardButton("✅ Monitor all", callback_data=f"tv:sall:{series_id}"),
         InlineKeyboardButton("⬜ Unmonitor all", callback_data=f"tv:snone:{series_id}")],
        [InlineKeyboardButton("◀️ Back", callback_data=f"tv:view:{series_id}")],
    ]

    lines = [
        f"📂 Seasons of {_series_label(series)}",
        "Tap a season to toggle monitoring (✅ monitored, ⬜ not). Numbers are files on disk / episodes.",
    ]
    if not series.get("monitored"):
        lines += ["", "⚠️ The show itself is unmonitored, so nothing will download. "
                      "Monitoring a season monitors the show too."]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _series_remove_confirm(series: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Ask what Sonarr's delete dialog asks: drop the entry, or the files on disk too."""
    series_id = series["id"]
    stats = series.get("statistics") or {}
    files = stats.get("episodeFileCount", 0)

    lines = [f"🗑️ Remove {_series_label(series)} from Sonarr?", ""]
    if series.get("path"):
        lines.append(f"📁 {series['path']}")
    if files:
        plural = "s" if files != 1 else ""
        lines.append(f"💾 {files} episode file{plural}, {format_size(stats.get('sizeOnDisk', 0))} on disk")
    else:
        lines.append("💾 Nothing downloaded yet")
    lines += ["", "Also delete the downloaded files from the drive?"]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Remove, keep files", callback_data=f"tv:rmk:{series_id}")],
        [InlineKeyboardButton("💥 Remove and delete files", callback_data=f"tv:rmd:{series_id}")],
        [InlineKeyboardButton("↩️ Cancel", callback_data=f"tv:view:{series_id}")],
    ])
    return "\n".join(lines), keyboard


async def manage_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /manageshow <title>."""
    await _manage_series_command(update, context, anime=False)


async def manage_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /manageanime <title>."""
    await _manage_series_command(update, context, anime=True)


async def _manage_series_command(update: Update, context: ContextTypes.DEFAULT_TYPE, anime: bool) -> None:
    if not update.message:
        return

    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        await send_search_prompt(update, "manageanime" if anime else "manageshow")
        return

    await manage_series_and_reply(update, context, " ".join(context.args), anime=anime)


async def manage_series_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  query: str, anime: bool) -> None:
    """Look a title up in the Sonarr library (not TVDB) and offer the matches.

    Shared by /manageshow, /manageanime and their ForceReply prompts. Looks in
    the requested kind first, then the whole library, so someone who reaches for
    /manageshow to find an anime still gets it.
    """
    message = update.effective_message
    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        await message.reply_text("❌ Sonarr client not initialized.")
        return

    library = await client.get_monitored_series()
    same_kind = [s for s in library if ((s.get("seriesType") or "").lower() == "anime") == anime]
    matches = find_in_library(same_kind, query) or find_in_library(library, query)

    if not matches:
        noun, command = ("anime", "anime") if anime else ("show", "show")
        await message.reply_text(f"❌ No {noun} matching '{query}' in the library. Use /{command} to add one.")
        return

    if len(matches) == 1:
        text, keyboard = series_panel(matches[0])
        await message.reply_text(text, reply_markup=keyboard)
        return

    keyboard = [[InlineKeyboardButton(f"{_series_emoji(s)} {_series_label(s)}", callback_data=f"tv:view:{s['id']}")]
                for s in matches]
    await message.reply_text("Which one?", reply_markup=InlineKeyboardMarkup(keyboard))


async def button_manage_series(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the manage panel buttons.

    tv:<view|mon|unmon|search|seasons|sall|snone|rm|rmk|rmd>:<sonarr id>
    tv:st:<sonarr id>:<season number>   (toggle one season)
    """
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        parts = query.data.split(":")
        action = parts[1]
        series_id = int(parts[2])
        season_number = int(parts[3]) if action == "st" else None
    except (IndexError, ValueError):
        await query.answer("❌ Invalid button data.", show_alert=True)
        return

    client: SonarrClient = context.bot_data.get("sonarr_client")
    if not client:
        await query.answer("❌ Sonarr client not initialized.", show_alert=True)
        return

    try:
        # Always re-read: the panel may be hours old, or edited in Sonarr since.
        series = await client.get_series(series_id)
        if not series:
            await query.answer()
            await safe_edit(query, "❌ That show is no longer in the Sonarr library.")
            return

        title = _series_label(series)
        user_id = update.effective_user.id

        if action == "view":
            await query.answer()
            await safe_edit(query, *series_panel(series))
            return

        if action == "seasons":
            await query.answer()
            await safe_edit(query, *_seasons_panel(series))
            return

        if action in ("mon", "unmon"):
            # Like Sonarr's bookmark toggle: only the show flag changes, season
            # choices are kept for when it's monitored again.
            series["monitored"] = action == "mon"
            updated = await client.update_series(series)
            if not updated:
                await query.answer(f"❌ Couldn't update {title}.", show_alert=True)
                return
            logger.info(f"user {user_id} set series {series_id} monitored={series['monitored']}")
            await query.answer("👁️ Show monitored" if action == "mon" else "🚫 Show unmonitored")
            await safe_edit(query, *series_panel(updated))
            return

        if action in ("st", "sall", "snone"):
            seasons = series.get("seasons", [])
            if action == "st":
                season = next((s for s in seasons if s.get("seasonNumber") == season_number), None)
                if not season:
                    await query.answer("❌ That season no longer exists.", show_alert=True)
                    return
                turning_on = not season.get("monitored", False)
                season["monitored"] = turning_on
                state = "monitored" if turning_on else "unmonitored"
                toast = f"{'✅' if turning_on else '⬜'} {_season_name(season_number)} {state}"
            else:
                turning_on = action == "sall"
                for season in seasons:
                    # "Monitor all" leaves specials alone, like Sonarr's own default.
                    if turning_on and season.get("seasonNumber") == 0:
                        continue
                    season["monitored"] = turning_on
                toast = "✅ All seasons monitored" if turning_on else "⬜ All seasons unmonitored"

            # A monitored season of an unmonitored show downloads nothing, which
            # is never what someone tapping "monitor" wants.
            if turning_on and not series.get("monitored"):
                series["monitored"] = True
                toast += " (show monitored too)"

            updated = await client.update_series(series)
            if not updated:
                await query.answer(f"❌ Couldn't update {title}.", show_alert=True)
                return
            logger.info(f"user {user_id} changed season monitoring on series {series_id}: {query.data}")
            await query.answer(toast)
            await safe_edit(query, *_seasons_panel(updated))
            return

        if action == "search":
            if not series.get("monitored"):
                await query.answer("⚠️ The show is unmonitored — monitor it first.", show_alert=True)
                return
            if not await client.trigger_series_search(series_id):
                await query.answer("❌ Couldn't start the search.", show_alert=True)
                return
            await query.answer(f"🔍 Searching monitored episodes of {title}")
            return

        if action == "rm":
            await query.answer()
            await safe_edit(query, *_series_remove_confirm(series))
            return

        if action in ("rmk", "rmd"):
            delete_files = action == "rmd"
            await query.answer("⏳ Removing...")
            if not await client.delete_series(series_id, delete_files=delete_files):
                await safe_edit(query, f"❌ Failed to remove {title} from Sonarr.")
                return
            logger.info(f"user {user_id} removed series {series_id} ({title}), deleteFiles={delete_files}")
            suffix = "and deleted its files from the drive" if delete_files else "— files left on the drive"
            await safe_edit(query, f"🗑️ Removed {title} from Sonarr {suffix}.")
            return

        await query.answer("❌ Unknown option.", show_alert=True)

    except Exception as e:
        logger.error(f"Error in button_manage_series ({query.data}): {e}")
        try:
            await query.answer("❌ An error occurred.", show_alert=True)
        except Exception:
            pass
