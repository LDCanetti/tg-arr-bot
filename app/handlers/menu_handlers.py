"""Tap-to-search menu and unknown-command help.

Lives in its own module because it drives both the Sonarr and Radarr handlers,
and importing it from either of those would be circular.

The flow is deliberately reply-based rather than stateful: tapping a button
sends a ForceReply prompt, and the user's reply is routed by reading the emoji
on the prompt they replied to. That survives a container restart (Watchtower
recreates this container nightly) and keeps two users searching in the same
group from clobbering each other. It also works under Telegram privacy mode,
which withholds ordinary group chatter from bots but always delivers replies to
the bot's own messages.
"""

import logging
from difflib import get_close_matches

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

from app.handlers.general_handlers import BOT_COMMANDS, is_authorized
from app.handlers.prompts import PROMPT_EMOJI, PROMPTS, send_search_prompt
from app.handlers.radarr_handlers import (
    add_top_movie_and_reply,
    manage_movie_and_reply,
    my_movies_command,
    search_movies_and_reply,
)
from app.handlers.sonarr_handlers import list_series, manage_series_and_reply, search_series_and_reply

logger = logging.getLogger(__name__)

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎬 Movie", callback_data="menu:movie"),
     InlineKeyboardButton("📺 Show", callback_data="menu:show")],
    [InlineKeyboardButton("🎌 Anime", callback_data="menu:anime"),
     InlineKeyboardButton("📚 Library", callback_data="menu:library")],
    [InlineKeyboardButton("⚙️ Manage library", callback_data="menu:manage")],
])

MANAGE_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎬 A movie", callback_data="menu:managemovie"),
     InlineKeyboardButton("📺 A show", callback_data="menu:manageshow")],
    [InlineKeyboardButton("🎌 An anime", callback_data="menu:manageanime")],
    [InlineKeyboardButton("◀️ Back", callback_data="menu:home")],
])

LIBRARY_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎬 Movies", callback_data="lib:movies"),
     InlineKeyboardButton("📺 Shows", callback_data="lib:shows")],
    [InlineKeyboardButton("🎌 Anime", callback_data="lib:anime")],
    [InlineKeyboardButton("◀️ Back", callback_data="menu:home")],
])

MENU_TEXT = "👋 What are you looking for?"

# Persistent keyboard pinned under the text box. The labels must be real
# commands: tapping one sends its text as an ordinary message, and privacy mode
# only delivers messages that start with a slash. "📚 My movies" would be sent
# by the user and never reach us.
QUICK_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("/menu"), KeyboardButton("/mymovies")],
        [KeyboardButton("/myshows"), KeyboardButton("/myanime")],
        [KeyboardButton("/help"), KeyboardButton("/hide")],
    ],
    resize_keyboard=True,   # compact rows instead of a half-screen grid
    is_persistent=True,     # stays put instead of collapsing behind the keyboard icon
    selective=True,         # only the person who asked for it sees it, not the whole group
)


async def _send_with_quick_keyboard(update: Update, text: str) -> None:
    """Attach the quick keyboard, targeted at the requesting user only.

    selective=True needs the message to be a reply to that user, otherwise
    Telegram shows the keyboard to everyone in the group.
    """
    await update.message.reply_text(
        text,
        reply_markup=QUICK_KEYBOARD,
        reply_to_message_id=update.message.message_id,
        allow_sending_without_reply=True,
    )


async def hide_keyboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /hide — take the quick keyboard away again."""
    if not update.message:
        return
    if not is_authorized(update, context):
        return
    await update.message.reply_text(
        "⌨️ Keyboard hidden. Send /start to bring it back.",
        reply_markup=ReplyKeyboardRemove(selective=True),
        reply_to_message_id=update.message.message_id,
        allow_sending_without_reply=True,
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu — show the tap-to-search buttons."""
    if not update.message:
        return
    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    await update.message.reply_text(MENU_TEXT, reply_markup=MAIN_MENU)


async def button_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the main menu buttons: menu:<movie|show|anime|library|manage|home|prompt kind>."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    choice = query.data.split(":", 1)[1]

    try:
        await query.answer()

        if choice == "home":
            await query.edit_message_text(MENU_TEXT, reply_markup=MAIN_MENU)
            return

        if choice == "library":
            await query.edit_message_text("📚 Which library?", reply_markup=LIBRARY_MENU)
            return

        if choice == "manage":
            await query.edit_message_text(
                "⚙️ What do you want to manage? Monitor, unmonitor or remove it next.",
                reply_markup=MANAGE_MENU,
            )
            return

        if choice not in PROMPTS:
            await query.answer("❌ Unknown option.", show_alert=True)
            return

        await send_search_prompt(update, choice)
    except Exception as e:
        logger.error(f"Error in button_menu ({choice}): {e}")


async def button_library(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the library submenu: lib:<movies|shows|anime>."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    choice = query.data.split(":", 1)[1]

    try:
        await query.answer()
        if choice == "movies":
            await my_movies_command(update, context)
        elif choice == "shows":
            await list_series(update, context, anime=False)
        elif choice == "anime":
            await list_series(update, context, anime=True)
    except Exception as e:
        logger.error(f"Error in button_library ({choice}): {e}")


async def handle_prompt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route a reply to one of our ForceReply prompts into the matching search."""
    message = update.effective_message
    replied = message.reply_to_message if message else None

    # Only our own prompts, identified by the emoji they open with.
    if not replied or not replied.from_user or not replied.from_user.is_bot:
        return
    if replied.from_user.id != context.bot.id:
        return

    kind = PROMPT_EMOJI.get((replied.text or "").split(" ", 1)[0])
    if not kind:
        return

    if not is_authorized(update, context):
        await message.reply_text("❌ You don't have permission to use this bot.")
        return

    query = (message.text or "").strip()
    if len(query) < 2:
        await message.reply_text("Please give me at least two characters to search for.")
        return

    logger.info(f"menu search: user {update.effective_user.id} looking for {kind} '{query}'")

    if kind == "movie":
        await search_movies_and_reply(update, context, query)
    elif kind == "addmovie":
        await add_top_movie_and_reply(update, context, query)
    elif kind == "managemovie":
        await manage_movie_and_reply(update, context, query)
    elif kind in ("manageshow", "manageanime"):
        await manage_series_and_reply(update, context, query, anime=(kind == "manageanime"))
    else:
        await search_series_and_reply(update, context, query, anime=(kind == "anime"))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with usage help when someone types a command we don't have.

    Registered last in the same handler group, so a real command always wins.
    """
    message = update.effective_message
    if not message or not message.text:
        return

    token = message.text.split()[0]          # e.g. "/movei@canetti_plex_bot"
    name, _, addressed_to = token[1:].partition("@")

    # In a group this fires for any unmatched "/..." — stay quiet if it was
    # plainly aimed at a different bot.
    if addressed_to and addressed_to.lower() != context.bot.username.lower():
        return

    if not is_authorized(update, context):
        return

    known = [c.command for c in BOT_COMMANDS]
    suggestion = get_close_matches(name.lower(), known, n=1, cutoff=0.5)

    lines = [f"❓ I don't know the command /{name}."]
    if suggestion:
        lines.append(f"Did you mean /{suggestion[0]}?")
    lines += [
        "",
        "Try one of these:",
        "  /movie <title> — search for a movie",
        "  /show <title> — search for a TV show",
        "  /anime <title> — search for anime",
        "  /managemovie, /manageshow, /manageanime <title> — monitor, unmonitor or remove",
        "  /menu — pick from buttons instead of typing",
        "  /help — full command list",
    ]
    await message.reply_text("\n".join(lines))
