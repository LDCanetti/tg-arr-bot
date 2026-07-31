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

    selective=True opens the reply box for two sets of people: those @mentioned in
    the text, and — when the message quotes one — the sender of the quoted message.
    Neither is free here:

    - mention_html builds a tg://user link for anyone without a public username.
      That is a text_mention entity, and selective does not count it.
    - PTB quotes by default in groups. A command quotes the user who sent it, so
      the box opens for them. A menu tap arrives as a callback on our own menu
      message, and quoting that targets the bot — the box then opens for nobody,
      the title is sent as an ordinary message, and privacy mode drops it before
      we ever see it. The prompt appears and replying does nothing.

    So quote the user only when the trigger was their own message, prefer a real
    @mention when they have a username, and where neither can target them, open
    the box for the whole chat rather than for no one.

    The emoji has to stay first either way — it is what routes the reply.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    from_bot = bool(message.from_user and message.from_user.is_bot)
    mention = f"@{user.username}" if user.username else user.mention_html()

    emoji, rest = PROMPTS[kind].split(" ", 1)
    await message.reply_text(
        f"{emoji} {mention} {rest}",
        reply_markup=ForceReply(selective=not from_bot or bool(user.username)),
        parse_mode="HTML",
        quote=not from_bot,
    )
