"""Release notes: /whatsnew for anyone, /announce to broadcast them once.

Broadcasting is a deliberate owner action rather than something done on
startup. The bot keeps no state, and Watchtower recreates the container
nightly, so an automatic "announce on boot" would re-send every morning.
"""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from app.handlers.general_handlers import is_authorized, is_owner

logger = logging.getLogger(__name__)

# Bump this whenever WHATS_NEW changes. Every running copy of the bot compares
# it with the last one it told its owners about and, on startup, sends the new
# notes once (see update_notice.py). Leave it alone for releases with nothing
# worth announcing, and nobody is messaged.
NOTES_VERSION = "2026.10.19"

# Update this with each release worth telling people about.
WHATS_NEW = (
    "🆕 What's new\n\n"
    "You can now manage what's already in the library, not just add to it:\n\n"
    "⚙️ /managemovie <title> — monitor, unmonitor, search or remove a movie\n"
    "⚙️ /manageshow <title> — the same for a show, plus monitor or unmonitor individual seasons\n"
    "⚙️ /manageanime <title> — the same for anime\n\n"
    "🗑️ Removing is for the bot's owners, and always asks first whether to keep the files "
    "or delete them from the drive.\n"
    "🔎 Searching for something that's already in the library now marks it ⚙️ — tap it to manage it "
    "instead of adding it twice.\n"
    "📋 /menu has a new ⚙️ Manage library button.\n\n"
    "Send /whatsnew to see this again, or /help for every command."
)

# Telegram allows ~30 messages a second across chats; stay well under it.
_SEND_INTERVAL = 0.1


def _recipients(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    """Every allowed group, then every allowed user privately, without repeats."""
    chats = context.bot_data.get("allowed_chats", []) + context.bot_data.get("allowed_users", [])
    return list(dict.fromkeys(chats))


async def whats_new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /whatsnew."""
    if not update.message:
        return
    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    await update.message.reply_text(WHATS_NEW)


async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /announce — preview the release notes and ask before broadcasting."""
    if not update.message:
        return
    if not is_owner(update, context):
        await update.message.reply_text("❌ Only the bot's owners (ALLOWED_USERS) can send announcements.")
        return

    # Count what will actually be sent: group chat ids are negative, users positive.
    recipients = _recipients(context)
    groups = sum(1 for c in recipients if c < 0)
    users = len(recipients) - groups
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📣 Send", callback_data="announce:send"),
        InlineKeyboardButton("✖️ Cancel", callback_data="announce:cancel"),
    ]])
    await update.message.reply_text(
        f"📣 This will be sent to {groups} group chat{'s' if groups != 1 else ''} and, privately, "
        f"to {users} user{'s' if users != 1 else ''}:\n\n"
        "────────\n"
        f"{WHATS_NEW}\n"
        "────────",
        reply_markup=keyboard,
    )


async def button_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle announce:<send|cancel>."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_owner(update, context):
        await query.answer("❌ Only the bot's owners can send announcements.", show_alert=True)
        return

    action = query.data.split(":", 1)[1]
    if action == "cancel":
        await query.answer()
        await query.edit_message_text("✖️ Announcement cancelled.")
        return
    if action != "send":
        await query.answer("❌ Unknown option.", show_alert=True)
        return

    # A double-tap must not broadcast twice.
    if context.bot_data.get("announcing"):
        await query.answer("⏳ Already sending.")
        return
    context.bot_data["announcing"] = True

    try:
        await query.answer("📣 Sending...")
        await query.edit_message_text("📣 Sending the announcement...")

        recipients = _recipients(context)
        failed = []
        for chat_id in recipients:
            try:
                await context.bot.send_message(chat_id, WHATS_NEW)
            except (Forbidden, BadRequest) as e:
                # Forbidden: the user never pressed Start, blocked the bot, or
                # it was removed from the group. Nothing to retry.
                logger.warning(f"announce: couldn't reach {chat_id}: {e}")
                failed.append(chat_id)
            await asyncio.sleep(_SEND_INTERVAL)

        sent = len(recipients) - len(failed)
        logger.info(f"announce: user {update.effective_user.id} sent release notes to {sent}/{len(recipients)} chats")
        text = f"📣 Sent to {sent} of {len(recipients)} chats."
        if failed:
            text += (
                "\n\nCouldn't reach: " + ", ".join(str(c) for c in failed) +
                "\nUsers have to press Start in a private chat with the bot before it can message them, "
                "and the bot has to still be in a group to post there."
            )
        await query.edit_message_text(text)
    finally:
        context.bot_data["announcing"] = False
