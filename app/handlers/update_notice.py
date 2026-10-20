"""Tell each deployment's owners about new features after they update.

Everyone running the image has their own bot, so the only way to reach them
is from inside it. On startup the bot compares NOTES_VERSION with the last
version it announced and, if they differ, privately sends its ALLOWED_USERS
the release notes once.

"The last version it announced" has to survive the container being recreated
(Watchtower does that nightly) without asking anyone to mount a volume. So it
lives on Telegram's side, as a marker at the end of the bot's short description
— the line on its profile page:

    Adds movies and shows to Sonarr/Radarr (tg-arr-bot 2026.10.19)

Any text the owner set in BotFather is kept; only the marker is added or
replaced. Groups aren't messaged — /announce does that, deliberately.
"""

import logging
import re

from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.handlers.announce_handlers import NOTES_VERSION, WHATS_NEW
from app.handlers.general_handlers import is_authorized
from app.version import APP_VERSION

logger = logging.getLogger(__name__)

# Telegram caps the short description at 120 characters.
_SHORT_DESCRIPTION_MAX = 120
_MARKER = re.compile(r"\s*\(tg-arr-bot ([^)\s]+)\)\s*$")
_DEFAULT_DESCRIPTION = "Adds movies and shows to Sonarr/Radarr"


def announced_version(short_description: str) -> str | None:
    """The notes version recorded in a short description, if any."""
    match = _MARKER.search(short_description or "")
    return match.group(1) if match else None


def with_marker(short_description: str, version: str) -> str:
    """The short description with its marker set to this version, owner's text kept."""
    marker = f"(tg-arr-bot {version})"
    text = _MARKER.sub("", short_description or "").strip() or _DEFAULT_DESCRIPTION
    room = _SHORT_DESCRIPTION_MAX - len(marker) - 1
    if len(text) > room:
        text = text[:room - 1].rstrip() + "…"
    return f"{text} {marker}"


async def notify_if_updated(bot: Bot, owners: list[int]) -> None:
    """Send the release notes to the owners once per NOTES_VERSION.

    The marker is written before anything is sent. If it can't be written,
    nothing is sent: an unrecorded notice would repeat on every restart, which
    is worse than none.
    """
    try:
        current = (await bot.get_my_short_description()).short_description or ""
    except TelegramError as e:
        logger.warning(f"update notice: couldn't read the short description, skipping: {e}")
        return

    previous = announced_version(current)
    if previous == NOTES_VERSION:
        return

    try:
        await bot.set_my_short_description(with_marker(current, NOTES_VERSION))
    except TelegramError as e:
        logger.warning(f"update notice: couldn't record version {NOTES_VERSION}, not announcing: {e}")
        return

    logger.info(f"update notice: release notes {previous or 'none'} -> {NOTES_VERSION}, telling {owners}")
    text = f"🆕 tg-arr-bot has been updated ({APP_VERSION}).\n\n{WHATS_NEW}"
    for chat_id in owners:
        try:
            await bot.send_message(chat_id, text)
        except TelegramError as e:
            # Usually an owner who never pressed Start in a private chat with the bot.
            logger.warning(f"update notice: couldn't reach {chat_id}: {e}")


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /version."""
    if not update.message:
        return
    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return
    await update.message.reply_text(
        f"🏷️ tg-arr-bot {APP_VERSION}\nRelease notes: {NOTES_VERSION} — /whatsnew to read them."
    )
