# tg-arr-bot — Telegram Sonarr & Radarr Bot

A Telegram bot for adding and managing movies, TV shows and anime in an existing
Sonarr/Radarr setup. Search from a chat, pick a result from inline buttons, and the
bot creates the entry and kicks off a search for it. Things already in the library
can be monitored, unmonitored (per season, for shows) or removed from the same chat.

Designed to be dropped into a group so everyone who uses your media server can
request media themselves, without any of them needing access to Sonarr or Radarr.

## Features

- 🎬 **Radarr** — search and add movies
- 📺 **Sonarr** — search and add TV shows
- 🎌 **Anime** — added as `seriesType: Anime` (absolute episode numbering) in its own root folder
- 🎛️ **Full monitoring choice** — all 11 of Sonarr's monitor options, not just "everything"
- ⚙️ **Library management** — monitor/unmonitor movies, shows and individual seasons; remove with or without deleting files
- 👥 **Group access** — authorize a whole group chat, or individual users
- 🔎 **Tap-to-search** — a button menu so members never have to learn the commands
- ⚡ **Async** throughout, one reused HTTP session per service

## Commands

| Command | What it does |
|---|---|
| `/menu` | Button menu — pick a category, reply with a title. No syntax to remember. |
| `/movie [title]` | Search movies, pick from buttons. No title? It asks for one. |
| `/show [title]` | Search TV shows, pick a result then a monitoring option |
| `/anime [title]` | Same as `/show`, but filed as anime |
| `/mymovies` | List the Radarr library (✅ = has a file, ⏳ = still wanted) |
| `/myshows` | List non-anime series |
| `/myanime` | List anime series |
| `/addmovie [title]` | Skip the menu and add the top match directly |
| `/addshow [title]` | Alias for `/show` (searches; does not blind-add) |
| `/managemovie [title]` | Find a movie in the library: monitor, unmonitor, search or remove it |
| `/manageshow [title]` | Same for a show, plus per-season monitoring |
| `/manageanime [title]` | Same as `/manageshow`, looking in anime first |
| `/whatsnew` | Release notes for the latest update |
| `/version` | Which build is running (date + commit) |
| `/announce` | Owners only (`ALLOWED_USERS`): send the release notes to every allowed group and user. Not in the `/` list. |
| `/start` | Welcome message plus the quick keyboard |
| `/hide` | Remove the quick keyboard |
| `/help` | The above, in chat |

The command list is published to Telegram on startup, so typing `/` offers them
as tappable suggestions in both private chats and groups.

Tapping one of those suggestions sends the command on its own, with no title
attached. The search commands treat that as the start of a search: they reply
asking for a title, with the reply box already open and aimed at whoever tapped.
Type the title, send, and the results come back as buttons. Nothing has to be
typed by hand.

Mistyped commands get a usage reminder with a closest-match suggestion, so
`/movei` replies "Did you mean /movie?".

### How adding works

Movies are added monitored, and Radarr searches for them immediately
(`searchForMovie`).

Shows and anime ask which seasons to monitor first. The choice maps to Sonarr's
`addOptions.monitor` enum, so it behaves exactly like the dropdown in Sonarr's
own "Add Series" dialog:

| Button | Sonarr value | Searches on add |
|---|---|---|
| 📺 All Episodes | `all` | yes |
| 🔮 Future Episodes | `future` | no |
| ❌ Missing Episodes | `missing` | yes |
| ✅ Existing Episodes | `existing` | no |
| 🕐 Recent Episodes | `recent` | yes |
| 🎬 Pilot Episode | `pilot` | yes |
| 🎞️ First Season | `firstSeason` | yes |
| ⏱️ Last Season | `lastSeason` | yes |
| 🎪 Monitor Specials | `monitorSpecials` | yes |
| 🚫 Unmonitor Specials | `unmonitorSpecials` | yes |
| ⛔ None | `none` | no |

Searches are scoped to the item just added — the bot does not trigger a
library-wide "search all missing", which would hammer your indexers.

### Managing the library

`/managemovie`, `/manageshow` and `/manageanime` look the title up in **your
library** (not TMDb/TVDB) and open a panel of buttons. A loose match is fine —
`/manageshow brekaing bad` still finds it. The same panel opens when a `/movie`,
`/show` or inline search turns up something you already have: those results are
marked ⚙️ and tapping one manages it instead of trying to add it twice. `/menu`
has a ⚙️ Manage library button too.

| Button | What it does |
|---|---|
| 👁️ Monitor / 🚫 Unmonitor | Flips the movie's or show's monitored flag, like the bookmark icon in the web UI |
| 📂 Seasons | One toggle per season (✅ monitored, ⬜ not), plus monitor/unmonitor all |
| 🔍 Search | Searches for this movie, or for the show's monitored episodes |
| 🗑️ Remove | Asks first — see below |

Season toggles behave like Sonarr's own: changing a season's monitoring flips
every episode in it to match. Monitoring a season of an unmonitored show also
monitors the show, since otherwise nothing would download. "Monitor all" leaves
Specials alone.

**Removing** shows the folder and how much is on disk, then asks the same
question as the web UI's delete dialog:

- 🗑️ **Remove, keep files** — drops it from Sonarr/Radarr, files stay on the drive
- 💥 **Remove and delete files** — also deletes the folder from disk. Not undoable.
- ↩️ **Cancel**

"Add list exclusion" is always left off, so a removed item can be re-added later.

**Only `ALLOWED_USERS` can remove.** Members of an `ALLOWED_CHATS` group can
monitor, unmonitor and search, but tapping Remove gets them "Only the bot's
owners can remove…". Deleting files can't be undone, so it stays with the
people you listed by ID.

### Announcing an update

After deploying a release, an owner sends `/announce`. The bot shows a preview of
the release notes and how many chats will get them, with **📣 Send** and
**✖️ Cancel** buttons. Send posts the notes to every `ALLOWED_CHATS` group and
privately to every `ALLOWED_USERS` member, then reports any it couldn't reach.
A private message only arrives if that user has pressed Start with the bot at
least once; Telegram doesn't let bots message anyone first.

It is manual on purpose. The bot keeps no state and Watchtower recreates the
container nightly, so announcing automatically on startup would repeat every day.
The notes live in `WHATS_NEW` in `app/handlers/announce_handlers.py`; edit them
for each release.

### Update notices

When you update the image and the new version comes with release notes, the
bot privately sends them to every `ALLOWED_USERS` member **once**, the first
time it starts — no command needed. Groups are left alone; use `/announce` for
those. Set `UPDATE_NOTICES=false` to turn it off.

To know what it has already announced without a volume, the bot keeps a small
marker at the end of its **short description** (the line on its profile page),
for example `Adds movies and shows to Sonarr/Radarr (tg-arr-bot 2026.10.19)`.
Any short description you set in BotFather is kept; only the marker in brackets
is added or updated. Watchtower recreating the container nightly doesn't
re-send anything.

Owners who have never pressed Start in a private chat with the bot can't be
messaged — Telegram doesn't let bots start conversations.

> **Maintainers:** a notice goes out only when `NOTES_VERSION` in
> `app/handlers/announce_handlers.py` changes. Update `WHATS_NEW` and bump
> `NOTES_VERSION` together for releases worth telling people about; leave both
> alone for fixes, and nobody is messaged.

## Prerequisites

- A working Sonarr (v3+ API) and Radarr instance the bot can reach over HTTP
- Root folders already registered in each, matching the paths you configure below
- Docker, or Python 3.11+
- A bot token from [@BotFather](https://t.me/BotFather)

## Setup

### 1. Create the bot

Talk to [@BotFather](https://t.me/BotFather):

- `/newbot` — get your `TELEGRAM_TOKEN`
- `/setinline` — **required** if you want `@yourbot movie Dune` inline search.
  Off by default, and while off every inline query is silently dropped.
- `/setprivacy` → **Enable** — recommended. The bot then only receives commands
  and replies to its own messages, rather than every message in your groups.
  Everything here works with privacy on. Note that toggling it does not affect
  groups the bot is already in until it is removed and re-added.

Get your numeric user ID from [@userinfobot](https://t.me/userinfobot).

### 2. Configure

```bash
cp .env.example .env
```

| Variable | Required | Default | Notes |
|---|---|---|---|
| `TELEGRAM_TOKEN` | yes | — | From @BotFather |
| `SONARR_URL` | yes | — | e.g. `http://sonarr:8989` |
| `SONARR_API_KEY` | yes | — | Sonarr → Settings → General |
| `RADARR_URL` | yes | — | e.g. `http://radarr:7878` |
| `RADARR_API_KEY` | yes | — | Radarr → Settings → General |
| `ALLOWED_USERS` | yes | — | Comma-separated Telegram user IDs |
| `ALLOWED_CHATS` | no | empty | Comma-separated **group** chat IDs (negative). Every member of a listed group may use the bot. |
| `QUALITY_PROFILE_ID` | no | `1` | Profile applied to everything added. `1` is usually "Any". |
| `SONARR_ROOT_SHOWS` | no | `/data/Plex/Shows` | Must be a registered root folder |
| `SONARR_ROOT_ANIME` | no | `/data/Plex/Anime` | Must be a registered root folder |
| `RADARR_ROOT_MOVIES` | no | `/data/Plex/Movies` | Must be a registered root folder |
| `UPDATE_NOTICES` | no | `true` | Send owners the release notes once after an update. `false` to turn off. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` also logs message contents |

Paths are as **Sonarr and Radarr** see them, not as the host sees them.

### 3. Run

Add the bot to the Compose file that already runs your Sonarr and Radarr, on the
same network so it can reach them by service name:

```yaml
  tg-bot:
    image: ldcanetti/tg-arr-bot:latest   # or: build: .
    container_name: tg-arr-bot
    environment:
      TELEGRAM_TOKEN: ${TELEGRAM_TOKEN}
      SONARR_URL: http://sonarr:8989
      SONARR_API_KEY: ${SONARR_API_KEY}
      RADARR_URL: http://radarr:7878
      RADARR_API_KEY: ${RADARR_API_KEY}
      ALLOWED_USERS: ${ALLOWED_USERS}
      ALLOWED_CHATS: ${ALLOWED_CHATS}
    restart: unless-stopped
    networks:
      - your-existing-network
```

```bash
docker compose up -d tg-bot
docker compose logs -f tg-bot
```

A healthy start looks like:

```
Bot started successfully! Version 2026.10.19-f078e43
Allowed users: [123456789]
Allowed group chats: [-1001234567890]
Published 17 commands to Telegram
Application started
```

#### Starting from nothing

If you don't have Sonarr and Radarr yet, the bundled `docker-compose.yml` brings
up the bot, Sonarr, Radarr and qBittorrent together:

```bash
mkdir -p data/Plex/{Shows,Anime,Movies} data/downloads
docker compose up -d
```

Then open Sonarr (`:8989`) and Radarr (`:7878`), finish each setup wizard, add
`/data/Plex/Shows`, `/data/Plex/Anime` and `/data/Plex/Movies` as root folders,
copy the API keys into `.env`, and `docker compose up -d tg-bot` to pick them up.
qBittorrent's web UI is on `:8080` and should use `/data/downloads` as its save
path.

Every service mounts the same single `./data` volume, and that is deliberate:
Sonarr and Radarr can only **hardlink** an import if the download directory and
the library are inside one container mount. Give them `/downloads` and `/tv` as
separate mounts and the kernel refuses the link with `EXDEV` — even when both
paths sit on the same host filesystem — so every import silently becomes a full
copy, doubling disk use while you seed. Keep one mount.

## Using it in a group

1. Add the bot to the group.
2. Get the group's chat ID and put it in `ALLOWED_CHATS`. The bot logs the IDs it
   accepts at startup; `getUpdates` or a bot like @userinfobot will tell you the
   chat ID.
3. Restart the bot and have someone send `/start`.

Any member of a listed group is authorized — you do not need to collect
individual user IDs. Be aware that this means **anyone added to that group can
add media to your library and change what's monitored.** Removing media and
deleting files stays limited to `ALLOWED_USERS`.

Negative IDs in `ALLOWED_USERS` are ignored: a chat ID can never match a user ID,
so group IDs belong in `ALLOWED_CHATS`.

> If a basic group is upgraded to a supergroup its ID changes to a `-100…` form
> and `ALLOWED_CHATS` will stop matching. The symptom is members suddenly being
> refused while private chats keep working.

### Inline queries

With inline mode enabled in BotFather, the bot can be used from any chat:

```
@yourbot movie The Matrix
@yourbot show Breaking Bad
@yourbot anime Demon Slayer
```

Results carry an "➕ Add" button, or "⚙️ Manage" for things already in the library. Inline queries are authorized by
`ALLOWED_USERS` **only** — Telegram sends no chat ID with them, so there is
nothing for `ALLOWED_CHATS` to match. Group members should use the commands
instead.

## Project structure

```
tg-arr-bot/
├── app/
│   ├── main.py                  # Entry point, handler registration
│   ├── version.py               # Build version baked in by CI
│   ├── config/settings.py       # Environment configuration
│   ├── clients/
│   │   ├── base.py              # Shared HTTP session and request helper
│   │   ├── sonarr.py            # Sonarr v3 API client
│   │   └── radarr.py            # Radarr v3 API client
│   └── handlers/
│       ├── general_handlers.py  # /start, /help, command list, authorization
│       ├── prompts.py           # "reply with a title" prompts and their routing
│       ├── menu_handlers.py     # /menu, quick keyboard, unknown-command help
│       ├── announce_handlers.py # /whatsnew, owner-only /announce broadcast
│       ├── update_notice.py     # one-time release notes after an update, /version
│       ├── sonarr_handlers.py   # /show, /anime, /myshows, /myanime, /manageshow, /manageanime
│       └── radarr_handlers.py   # /movie, /addmovie, /mymovies, /managemovie
├── docker-compose.yml           # Example standalone stack (see caveat above)
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Troubleshooting

**Bot doesn't respond at all**
Check `docker compose logs tg-bot`. A bad token fails at startup. Note that only
one process may poll a given token — a second copy running elsewhere will cause
both to miss updates.

**"You don't have permission"**
Your user ID isn't in `ALLOWED_USERS`, or the group's ID isn't in
`ALLOWED_CHATS`. The startup log prints both lists as parsed.

**Adds fail with no obvious error**
Almost always the root folder. The configured path must exactly match a
registered root folder in Sonarr/Radarr, as those apps see it. Check
`GET /api/v3/rootFolder`.

**Everything is added at the wrong quality**
`QUALITY_PROFILE_ID` defaults to `1`, which is typically the "Any" profile. List
your profiles with `GET /api/v3/qualityprofile` and set the ID you want.

**Inline search does nothing**
Inline mode is off in BotFather (`/setinline`), or you aren't in `ALLOWED_USERS`.

**Typing `/` shows no command list**
The list is published on startup; check for "Published 17 commands" in the log.
Telegram caches it client-side, so reopen the chat.

**The bot sees group messages it shouldn't**
Privacy mode changes don't apply to groups the bot already belongs to. Remove it
from the group and add it back.

## Development

```bash
pip install -r requirements.txt
python -m app.main
```

Settings are read from `.env` via pydantic-settings, so a local run picks up the
same file the container uses.

## License

MIT.
