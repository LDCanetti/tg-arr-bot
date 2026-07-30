"""ForceReply search prompts, shared by the /menu buttons and the commands.

Tapping a command out of Telegram's "/" list sends it with no arguments. That is
the normal way people use the list, so a bare /movie asks for a title with one of
these prompts rather than printing usage at someone who just tapped a button.

Kept in its own module because both menu_handlers and the Sonarr/Radarr handlers
need it, and menu_handlers already imports those two.
"""

import logging

from telegram import ForceReply, Update

logger = logging.getLogger(__name__)

# The leading emoji doubles as the routing key when the user replies, so each
# kind needs its own. See handle_prompt_reply.
PROMPTS = {
    "movie": "🎬 Reply to this message with a movie title:",
    "show": "📺 Reply to this message with a TV show title:",
    "anime": "🎌 Reply to this message with an anime title:",
    "addmovie": "⚡ Reply to this message with a movie title — I'll add the top match:",
}
PROMPT_EMOJI = {text.split()[0]: kind for kind, text in PROMPTS.items()}


async def send_search_prompt(update: Update, kind: str) -> None:
    """Ask for a title, with the reply box aimed at just this user.

    ForceReply(selective=True) only opens for people the message mentions, hence
    the mention wedged in after the emoji — the emoji has to stay first for the
    reply routing to work.
    """
    message = update.effective_message
    if not message:
        return

    emoji, rest = PROMPTS[kind].split(" ", 1)
    await message.reply_text(
        f"{emoji} {update.effective_user.mention_html()} {rest}",
        reply_markup=ForceReply(selective=True),
        parse_mode="HTML",
    )
