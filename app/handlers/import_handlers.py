"""Alerts for downloads stuck waiting on manual import, and buttons to resolve them.

When Sonarr or Radarr can't import a finished download on its own (not an
upgrade, couldn't match the episode, sample-only, ...) it parks it in the
Activity queue with an orange warning and waits for someone to open the
Manual Import dialog. Nothing tells you, so episodes sit there for weeks.

A repeating job polls both queues. Each newly stuck download gets one alert
with Review / Reject / Dismiss buttons that drive the same API calls the web UI
uses: manualimport + the ManualImport command to accept, and queue removal
with blocklisting to reject and search again.

Which downloads were already announced is kept in memory only, so after a
restart anything still stuck is announced again — a reminder, not a bug.

Buttons carry imp:<s|r>:<action>:<queue id>. The queue is re-read on every
tap, so a stale alert for something since handled says so instead of acting.
"""

import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.handlers.general_handlers import format_size, is_authorized, is_owner, safe_edit

logger = logging.getLogger(__name__)

# Callback/service code -> (bot_data key of the client, display name).
SERVICES = {
    "s": ("sonarr_client", "Sonarr"),
    "r": ("radarr_client", "Radarr"),
}

# Actions that change something; reviewing is read-only and open to everyone allowed.
OWNER_ACTIONS = ("ok", "rj", "rjy", "dis")

# Telegram limits messages to 4096 characters, so every list is capped and each
# view goes through _clip as a final guard.
_MAX_MESSAGE = 4000
_MAX_REASONS = 8
_MAX_FILES = 6
_MAX_REJECTIONS_PER_FILE = 3
_MAX_REASON_CHARS = 200
_MAX_EPISODE_CODES = 6

# New alerts sent per check, and the pause between sends. A restart re-announces
# the whole backlog; this keeps that under Telegram's flood limits (~20/min in a
# group). Whatever is left goes out on the next check.
_MAX_NEW_ALERTS_PER_CHECK = 10
_SEND_INTERVAL = 1.0

# After an "Import anyway" that was still running when we stopped waiting,
# refuse a second one for this long. Big cross-disk copies take a while.
_IMPORT_RUNNING_GRACE = 300


# --- Reading the queue ----------------------------------------------------------

def needs_attention(item: dict) -> bool:
    """True for queue items the Activity tab shows as waiting on a human.

    importBlocked always needs someone. importPending with a warning is the
    "Downloaded - Waiting to Import" state with a reason attached; without a
    warning it's just an import that's about to happen.
    """
    state = item.get("trackedDownloadState")
    status = item.get("trackedDownloadStatus")
    return state == "importBlocked" or (state == "importPending" and status in ("warning", "error"))


def pending_downloads(queue: list) -> dict[str, list[dict]]:
    """Stuck downloads keyed by download id.

    Sonarr has one queue record per episode, so a multi-episode release or a
    season pack shows up as several records sharing a download id.
    """
    groups: dict[str, list[dict]] = {}
    for item in queue:
        if needs_attention(item) and item.get("downloadId"):
            groups.setdefault(item["downloadId"], []).append(item)
    return groups


def _episode_codes(episodes: list[dict]) -> str:
    """'S01E01, S01E02', sorted, and cut short for complete-series packs."""
    ordered = sorted(episodes, key=lambda e: (e.get("seasonNumber", 0), e.get("episodeNumber", 0)))
    codes = [f"S{e.get('seasonNumber', 0):02d}E{e.get('episodeNumber', 0):02d}" for e in ordered]
    if len(codes) > _MAX_EPISODE_CODES:
        codes = codes[:_MAX_EPISODE_CODES] + [f"…and {len(codes) - _MAX_EPISODE_CODES} more"]
    return ", ".join(codes)


def media_label(service: str, items: list[dict]) -> str:
    """What the download is for: '📺 Show S01E02 — "Title"' or '🎬 Movie (Year)'.

    Downloads Sonarr/Radarr couldn't match to anything come without a series,
    episode or movie, and are labelled by their release name instead.
    """
    first = items[0]
    if service == "s":
        series = first.get("series")
        if not series:
            return f"📺 Unknown series — {first.get('title', 'unnamed release')}"
        codes = _episode_codes([i["episode"] for i in items if i.get("episode")])
        label = f"📺 {series.get('title', 'Unknown show')} {codes}".rstrip()
        if len(items) == 1 and (first.get("episode") or {}).get("title"):
            label += f' — "{first["episode"]["title"]}"'
        return label
    movie = first.get("movie")
    if not movie:
        return f"🎬 Unknown movie — {first.get('title', 'unnamed release')}"
    return f"🎬 {movie.get('title', 'Unknown movie')} ({movie.get('year', 'N/A')})"


def _shorten(reason: str) -> str:
    """One rejection or warning, cut to a readable length."""
    return reason if len(reason) <= _MAX_REASON_CHARS else reason[:_MAX_REASON_CHARS - 1].rstrip() + "…"


def _clip(text: str) -> str:
    """Last line of defence against Telegram's 4096-character message limit."""
    if len(text) <= _MAX_MESSAGE:
        return text
    return text[:_MAX_MESSAGE - 40].rstrip() + "\n…(cut — see the Activity tab)"


def _quality_name(quality: dict | None) -> str:
    return ((quality or {}).get("quality") or {}).get("name") or "Unknown quality"


def _reasons(items: list[dict]) -> list[str]:
    """The warning text the Activity tab shows, without repeats."""
    reasons: list[str] = []
    for item in items:
        for status_message in item.get("statusMessages") or []:
            for message in status_message.get("messages") or []:
                if message not in reasons:
                    reasons.append(message)
        if item.get("errorMessage") and item["errorMessage"] not in reasons:
            reasons.append(item["errorMessage"])
    return reasons or ["No reason given — check the Activity tab."]


def alert_view(service: str, items: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    """The alert: what it is, which release, and why it's stuck."""
    first = items[0]
    name = SERVICES[service][1]
    reasons = _reasons(items)
    lines = [
        f"⚠️ {name} can't import a download on its own",
        "",
        media_label(service, items),
        f"📦 {first.get('title', 'Unknown release')}",
        f"{_quality_name(first.get('quality'))} · {format_size(first.get('size', 0))}",
        "",
        "Why:",
    ]
    lines += [f"• {_shorten(r)}" for r in reasons[:_MAX_REASONS]]
    if len(reasons) > _MAX_REASONS:
        lines.append(f"• …and {len(reasons) - _MAX_REASONS} more in the Activity tab")

    queue_id = first["id"]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Review files", callback_data=f"imp:{service}:rv:{queue_id}"),
         InlineKeyboardButton("🚫 Reject & search again", callback_data=f"imp:{service}:rj:{queue_id}")],
        [InlineKeyboardButton("🙈 Dismiss", callback_data=f"imp:{service}:dis:{queue_id}")],
    ])
    return _clip("\n".join(lines)), keyboard


# --- Building the import --------------------------------------------------------

def plan_import(service: str, items: list[dict], candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Turn Manual Import candidates into ManualImport command files, plus a description.

    Mirrors what you'd do in the dialog: take each file with whatever Sonarr or
    Radarr matched it to, falling back to the queue's own match when the file
    wasn't matched (the usual "matched by ID, automatic import is not possible"
    case). Samples are left out. A file is only imported when it's clear what
    it is — anything ambiguous stays for the web UI.

    Returns (files to import, description lines).
    """
    first = items[0]
    download_id = first.get("downloadId")
    queue_episode_ids = [i["episodeId"] for i in items if i.get("episodeId")]

    def is_sample(candidate: dict) -> bool:
        return any("sample" in (r.get("reason") or "").lower() for r in candidate.get("rejections") or [])

    real_files = [c for c in candidates if not is_sample(c)]
    files, lines = [], []

    for candidate in candidates[:_MAX_FILES]:
        name = candidate.get("relativePath") or candidate.get("name") or candidate.get("path", "?")
        quality = candidate.get("quality") or first.get("quality")
        languages = candidate.get("languages") or first.get("languages") or []
        rejections = [r.get("reason") for r in candidate.get("rejections") or [] if r.get("reason")]

        lines.append(f"📄 {name}")
        lines.append(f"    {_quality_name(quality)} · {format_size(candidate.get('size', 0))}")

        if is_sample(candidate):
            lines.append("    ⏭️ Sample — won't be imported")
            continue

        entry = {
            "path": candidate.get("path"),
            "folderName": candidate.get("folderName"),
            "quality": quality,
            "languages": languages,
            "releaseGroup": candidate.get("releaseGroup"),
            "indexerFlags": candidate.get("indexerFlags") or 0,
            "downloadId": download_id,
        }

        if service == "s":
            series_id = (candidate.get("series") or {}).get("id") or first.get("seriesId")
            episode_ids = [e["id"] for e in candidate.get("episodes") or [] if e.get("id")]
            if not episode_ids and len(real_files) == 1:
                # One file, unmatched: it can only be the episode(s) the queue grabbed it for.
                episode_ids = queue_episode_ids
            if not series_id or not episode_ids:
                lines.append("    ❓ Can't tell which episode this is — map it in Sonarr's Activity tab")
                continue
            entry.update({
                "seriesId": series_id,
                "episodeIds": episode_ids,
                "episodeFileId": candidate.get("episodeFileId"),
                "releaseType": candidate.get("releaseType") or "unknown",
            })
            codes = _episode_codes(candidate.get("episodes") or [])
            lines.append(f"    → {codes or media_label(service, items)[2:]}")
        else:
            movie_id = (candidate.get("movie") or {}).get("id")
            if not movie_id and len(real_files) == 1:
                # One file, unmatched: it can only be the movie the queue grabbed it for.
                # With several (an extra, a second cut) guessing could import the wrong one.
                movie_id = first.get("movieId")
            if not movie_id:
                lines.append("    ❓ Can't tell which movie this is — map it in Radarr's Activity tab")
                continue
            entry["movieId"] = movie_id
            lines.append(f"    → {media_label(service, items)[2:]}")

        lines += [f"    ⚠️ {_shorten(r)}" for r in rejections[:_MAX_REJECTIONS_PER_FILE]]
        if len(rejections) > _MAX_REJECTIONS_PER_FILE:
            lines.append(f"    …and {len(rejections) - _MAX_REJECTIONS_PER_FILE} more")
        files.append(entry)

    if len(candidates) > _MAX_FILES:
        lines.append(f"…and {len(candidates) - _MAX_FILES} more files, left for the web UI")
    return files, lines


def review_view(service: str, items: list[dict], candidates: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    queue_id = items[0]["id"]
    name = SERVICES[service][1]
    files, lines = plan_import(service, items, candidates)

    text = [f"🔍 {media_label(service, items)}", ""]
    if not candidates:
        text.append(f"{name} found no importable files in this download.")
    text += lines
    rows = []
    if files:
        text += ["", f"✅ Import anyway brings in {len(files)} file{'s' if len(files) != 1 else ''} "
                     "despite the warnings above — like ticking them in the Manual Import dialog."]
        rows.append([InlineKeyboardButton("✅ Import anyway", callback_data=f"imp:{service}:ok:{queue_id}")])
    else:
        text += ["", f"Nothing here can be imported from Telegram. Fix it in {name}'s Activity tab, or reject it."]
    rows.append([InlineKeyboardButton("🚫 Reject & search again", callback_data=f"imp:{service}:rj:{queue_id}")])
    rows.append([InlineKeyboardButton("◀️ Back", callback_data=f"imp:{service}:back:{queue_id}")])
    return _clip("\n".join(text)), InlineKeyboardMarkup(rows)


def reject_confirm_view(service: str, items: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    queue_id = items[0]["id"]
    name = SERVICES[service][1]
    text = (
        f"🚫 Reject this download?\n\n{media_label(service, items)}\n📦 {items[0].get('title', '')}\n\n"
        f"It will be removed from the download client (its files are deleted), the release "
        f"is blocklisted so it isn't grabbed again, and {name} searches for another."
    )
    text = _clip(text)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Yes, reject it", callback_data=f"imp:{service}:rjy:{queue_id}")],
        [InlineKeyboardButton("◀️ Back", callback_data=f"imp:{service}:back:{queue_id}")],
    ])
    return text, keyboard


# --- Alert bookkeeping ------------------------------------------------------------
#
# bot_data["import_alerts"]: "<service>:<download id>" -> {
#     "label":     what the download is for, for outcome messages,
#     "messages":  every (chat, message) showing this alert, so all copies can be updated,
#     "announced": the job got it to at least one alert recipient,
#     "closed":    someone acted on it here (imported, rejected, dismissed),
#     "misses":    consecutive checks it wasn't stuck — see check_imports,
# }
# bot_data["imports_running"]: key -> when an "Import anyway" was left running,
# so a second tap doesn't start a duplicate import.
# "announced" is separate from "messages" on purpose: an alert shown by /imports
# or a failed send must not stop the owners from getting theirs.

def _alerts(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.setdefault("import_alerts", {})


def _entry(context: ContextTypes.DEFAULT_TYPE, service: str, items: list[dict]) -> dict:
    key = f"{service}:{items[0]['downloadId']}"
    return _alerts(context).setdefault(
        key, {"label": media_label(service, items), "messages": [], "announced": False, "closed": False, "misses": 0}
    )


async def _close_alert(context: ContextTypes.DEFAULT_TYPE, key: str, text: str, skip=None) -> None:
    """Replace every copy of an alert with an outcome, except the one already edited."""
    entry = _alerts(context).get(key)
    if not entry:
        return
    entry["closed"] = True
    for chat_id, message_id in entry["messages"]:
        if (chat_id, message_id) == skip:
            continue
        try:
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        except TelegramError as e:
            logger.debug(f"import alert: couldn't update {chat_id}/{message_id}: {e}")


async def _send_alert(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service: str, items: list[dict]) -> bool:
    """Send one copy of an alert and track it. Returns whether it was delivered."""
    entry = _entry(context, service, items)
    text, keyboard = alert_view(service, items)
    try:
        message = await context.bot.send_message(chat_id, text, reply_markup=keyboard)
    except TelegramError as e:
        # Usually a user who never pressed Start with the bot, or a flood limit.
        logger.warning(f"import alert: couldn't send to {chat_id}: {e}")
        return False
    entry["messages"].append((chat_id, message.message_id))
    return True


async def check_imports(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Repeating job: alert on newly stuck downloads, close alerts handled elsewhere."""
    alerts = _alerts(context)
    recipients = context.bot_data.get("import_alert_chats", [])
    sent_this_check = 0

    for service, (client_key, name) in SERVICES.items():
        client = context.bot_data.get(client_key)
        if not client:
            continue
        queue = await client.get_queue()
        if queue is None:
            # Unreachable: leave every alert as it is rather than calling them resolved.
            continue

        pending = pending_downloads(queue)
        for download_id, items in pending.items():
            entry = alerts.get(f"{service}:{download_id}")
            if entry:
                entry["misses"] = 0
                if entry["announced"] or entry["closed"]:
                    continue
            # Budget counts messages, not downloads. The first download of a check
            # always goes, so a long recipient list can't stall alerts entirely.
            if sent_this_check and sent_this_check + len(recipients) > _MAX_NEW_ALERTS_PER_CHECK:
                continue  # the rest go out on the next check
            logger.info(f"import alert: {name} download {download_id} needs manual import ({items[0].get('title')})")
            delivered = False
            for chat_id in recipients:
                if sent_this_check:
                    await asyncio.sleep(_SEND_INTERVAL)
                delivered = await _send_alert(context, chat_id, service, items) or delivered
                sent_this_check += 1
            # Only counts once someone actually got it; otherwise retry next check.
            _entry(context, service, items)["announced"] = delivered

        # Sonarr/Radarr re-check blocked downloads now and then, so one can look
        # unstuck for a moment and then block again. Only call it resolved after
        # two checks in a row, or a dismissed alert would come straight back.
        current = {f"{service}:{d}" for d in pending}
        for key in [k for k in alerts if k.startswith(f"{service}:") and k not in current]:
            entry = alerts[key]
            entry["misses"] = entry.get("misses", 0) + 1
            if entry["misses"] < 2:
                continue
            if not entry["closed"]:
                await _close_alert(context, key, f"✅ {entry['label']}\nNo longer waiting in {name}.")
            del alerts[key]
            context.bot_data.get("imports_running", {}).pop(key, None)


# --- Command and buttons ----------------------------------------------------------

async def imports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /imports — list every download currently waiting on manual import."""
    if not update.message:
        return
    if not is_authorized(update, context):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    found = failed = 0
    for service, (client_key, name) in SERVICES.items():
        client = context.bot_data.get(client_key)
        queue = await client.get_queue() if client else None
        if queue is None:
            await update.message.reply_text(f"❌ Couldn't reach {name}.")
            continue
        for items in pending_downloads(queue).values():
            found += 1
            if found > 10:
                continue
            if found > 1:
                await asyncio.sleep(_SEND_INTERVAL)  # same flood pacing as the job
            if await _send_alert(context, update.message.chat_id, service, items):
                # Asking for it again means you want to act on it: a dismissed
                # alert is live again, so this copy is updated when it clears.
                _entry(context, service, items)["closed"] = False
            else:
                failed += 1

    if not found:
        await update.message.reply_text("✅ Nothing is waiting on a manual import.")
    elif found > 10:
        await update.message.reply_text(f"…and {found - 10} more. Clear some and run /imports again.")
    if failed:
        await update.message.reply_text(f"⚠️ {failed} couldn't be shown (Telegram refused). Try /imports again shortly.")


async def button_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle imp:<s|r>:<rv|ok|rj|rjy|dis|back>:<queue id>."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not is_authorized(update, context):
        await query.answer("❌ You don't have permission to use this bot.", show_alert=True)
        return

    try:
        _, service, action, raw_id = query.data.split(":", 3)
        queue_id = int(raw_id)
        client_key, name = SERVICES[service]
    except (ValueError, KeyError):
        await query.answer("❌ Invalid button data.", show_alert=True)
        return

    if action in OWNER_ACTIONS and not is_owner(update, context):
        await query.answer("🔒 Only the bot's owners can import, reject or dismiss downloads.", show_alert=True)
        return

    client = context.bot_data.get(client_key)
    if not client:
        await query.answer(f"❌ {name} client not initialized.", show_alert=True)
        return

    try:
        # Always re-read: the alert may be hours old and handled in the web UI since.
        queue = await client.get_queue()
        if queue is None:
            await query.answer(f"❌ Couldn't reach {name}. Try again in a minute.", show_alert=True)
            return
        here = (query.message.chat_id, query.message.message_id) if query.message else None
        pending = pending_downloads(queue)

        # Buttons carry one queue record's id, but a season pack has one record
        # per episode and they leave the queue one by one. Find the download by
        # that record, or else by which alert was tapped.
        item = next((i for i in queue if i.get("id") == queue_id), None)
        download_id = item.get("downloadId") if item else None
        if download_id not in pending and here:
            download_id = next((k.split(":", 1)[1] for k, e in _alerts(context).items()
                                if k.startswith(f"{service}:") and here in e["messages"]), download_id)
        if download_id not in pending:
            await query.answer()
            await safe_edit(query, f"✅ This download is no longer waiting in {name} — it has been dealt with already.")
            return

        items = pending[download_id]
        key = f"{service}:{download_id}"
        label = media_label(service, items)
        # Track it from here, so Dismiss, Import and Reject are recorded even
        # before the first check. Not marked announced: a group member tapping
        # an /imports copy mustn't stop the owners' alert.
        entry = _entry(context, service, items)
        if here and here not in entry["messages"]:
            entry["messages"].append(here)

        if action == "back":
            await query.answer()
            await safe_edit(query, *alert_view(service, items))
            return

        if action == "rj":
            await query.answer()
            await safe_edit(query, *reject_confirm_view(service, items))
            return

        if action == "dis":
            await query.answer("🙈 Dismissed")
            text = f"🙈 Dismissed: {label}\nStill waiting in {name}'s Activity tab — /imports lists it."
            await safe_edit(query, text)
            await _close_alert(context, key, text, skip=here)
            return

        if action in ("rv", "ok"):
            candidates = await client.get_manual_import(download_id)
            if candidates is None:
                await query.answer(f"❌ Couldn't read the download's files from {name}.", show_alert=True)
                return

            if action == "rv":
                await query.answer()
                await safe_edit(query, *review_view(service, items, candidates))
                return

            running = context.bot_data.setdefault("imports_running", {})
            if time.monotonic() - running.get(key, -1e9) < _IMPORT_RUNNING_GRACE:
                await query.answer(f"⏳ {name} is still importing this — give it a minute.", show_alert=True)
                return

            files, _ = plan_import(service, items, candidates)
            if not files:
                await query.answer(f"Nothing here can be imported from Telegram — use {name}'s Activity tab.",
                                   show_alert=True)
                return

            await query.answer("⏳ Importing...")
            await safe_edit(query, f"⏳ Importing {label}...")
            command_id = await client.manual_import(files)
            command = await client.wait_for_command(command_id) if command_id else None
            status = (command or {}).get("status")
            logger.info(f"import: user {update.effective_user.id} imported {name} download {download_id}: {status}")

            # A "completed" command doesn't prove the file went in — Sonarr/Radarr
            # report the command done even when they skip the file. The download
            # leaving the queue is the real signal, so check that before closing.
            after = await client.get_queue() if status == "completed" else None
            still_waiting = after is None or download_id in pending_downloads(after)

            if status == "completed" and not still_waiting:
                text = f"✅ Imported {label}."
                running.pop(key, None)
                await safe_edit(query, text)
                await _close_alert(context, key, text, skip=here)
                return

            # Not confirmed: keep the alert's buttons so it can be retried or rejected.
            if command_id and status not in ("completed", "failed", "aborted", "cancelled", "orphaned"):
                running[key] = time.monotonic()
            else:
                running.pop(key, None)
            if status == "completed":
                note = f"⚠️ {name} ran the import, but the download is still waiting. Check the Activity tab."
            elif status in ("failed", "aborted", "cancelled", "orphaned"):
                note = f"❌ {name} couldn't import it: {(command or {}).get('message') or 'no reason given'}"
            elif command_id:
                note = f"⏳ {name} is still importing. This alert updates once the download leaves the queue."
            else:
                note = f"❌ {name} refused the import. Check its logs."
            alert_text, keyboard = alert_view(service, items)
            await safe_edit(query, _clip(f"{note}\n\n{alert_text}"), keyboard)
            return

        if action == "rjy":
            await query.answer("⏳ Rejecting...")
            if not await client.remove_queue_item(queue_id, blocklist=True, search_again=True):
                await safe_edit(query, f"❌ {name} wouldn't remove {label}. Try the Activity tab.")
                return
            logger.info(f"import: user {update.effective_user.id} rejected {name} download {download_id}")
            text = (f"🚫 Rejected {label}.\nThe release is blocklisted and {name} is searching for another "
                    "(if \"Redownload Failed\" is on in its settings, the default).")
            await safe_edit(query, text)
            await _close_alert(context, key, text, skip=here)
            return

        await query.answer("❌ Unknown option.", show_alert=True)

    except Exception as e:
        logger.error(f"Error in button_import ({query.data}): {e}")
        try:
            await query.answer("❌ An error occurred.", show_alert=True)
        except Exception:
            pass
