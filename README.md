# tg-arr-bot - Telegram Sonarr & Radarr Bot

A Docker containerized Telegram bot for managing your Sonarr and Radarr media libraries through an intuitive chat interface.

## Features

- 🎬 **Radarr Integration**: Search and add movies to your library via Telegram
- 📺 **Sonarr Integration**: Search and add TV shows to your library via Telegram
- 🔐 **Secure**: User whitelist to restrict access to the bot
- 🐳 **Docker Compose**: Ready-to-deploy with Sonarr and Radarr services
- ⚡ **Async Operations**: Built with async/await for responsive bot interactions

## Available Commands

### Movies (Radarr)
- `/movie <title>` - Search for movies
- `/addmovie <title>` - Add a movie to Radarr
- `/mymovies` - List monitored movies (coming soon)

### TV Shows (Sonarr)
- `/show <title>` - Search for TV shows
- `/addshow <title>` - Add a TV show to Sonarr
- `/myshows` - List monitored shows (coming soon)

### General
- `/start` - Welcome message and command overview
- `/help` - Show all available commands

## Prerequisites

- Docker & Docker Compose installed
- Telegram Bot Token (from @BotFather)
- Sonarr API Key
- Radarr API Key

## Quick Start

### 1. Clone and Setup

```bash
cd /path/to/tg-arr-bot
cp .env.example .env
```

### 2. Configure Environment

Edit `.env` with your settings:

```env
TELEGRAM_TOKEN=your_bot_token_here
SONARR_API_KEY=your_sonarr_key_here
RADARR_API_KEY=your_radarr_key_here
ALLOWED_USERS=123456789,987654321
```

To get your Telegram user ID, send `/start` to @userinfobot

### 3. Start Services

```bash
docker-compose up -d
```

This will start:
- **Bot**: Telegram bot service
- **Sonarr**: TV show management (http://localhost:8989)
- **Radarr**: Movie management (http://localhost:7878)

### 4. Configure Sonarr & Radarr

1. Open http://localhost:8989 for Sonarr
2. Open http://localhost:7878 for Radarr
3. Complete the setup wizard in each application
4. Generate API keys in settings
5. Update your `.env` file with the API keys

### 5. Restart Bot

```bash
docker-compose restart bot
```

## Project Structure

```
tg-arr-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Bot entry point
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py         # Environment configuration
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── sonarr.py          # Sonarr API client
│   │   └── radarr.py          # Radarr API client
│   └── handlers/
│       ├── __init__.py
│       ├── general_handlers.py # /start, /help commands
│       ├── sonarr_handlers.py  # /show, /addshow commands
│       └── radarr_handlers.py  # /movie, /addmovie commands
├── docker-compose.yml          # Multi-service orchestration
├── Dockerfile                  # Bot container image
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
└── README.md                  # This file
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Telegram Bot Token from @BotFather | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `SONARR_URL` | Sonarr API base URL | `http://sonarr:8989` |
| `SONARR_API_KEY` | Sonarr API authentication key | `abc123def456` |
| `RADARR_URL` | Radarr API base URL | `http://radarr:7878` |
| `RADARR_API_KEY` | Radarr API authentication key | `xyz789uvm123` |
| `ALLOWED_USERS` | Comma-separated Telegram user IDs | `123456789,987654321` |

## Accessing Services

After starting docker-compose:

| Service | URL | Port |
|---------|-----|------|
| Sonarr | http://localhost:8989 | 8989 |
| Radarr | http://localhost:7878 | 7878 |

## Usage Examples

### Search for a Movie
```
User: /movie The Matrix
Bot: 🔍 Searching for: The Matrix
     🎬 Found movies:
     1. The Matrix (1999)
        ID: 603
     2. The Matrix Reloaded (2003)
        ID: 234
     ...
     Use `/addmovie The Matrix` to add a movie.

User: /addmovie The Matrix
Bot: ✅ Added 'The Matrix' to Radarr!
```

### Search for a TV Show
```
User: /show Breaking Bad
Bot: 🔍 Searching for: Breaking Bad
     📺 Found TV shows:
     1. Breaking Bad (2008)
        ID: 81189
     ...
     Use `/addshow Breaking Bad` to add a show.

User: /addshow Breaking Bad
Bot: ✅ Added 'Breaking Bad' to Sonarr!
```

## Troubleshooting

### Bot not responding
- Check Telegram token is correct: `TELEGRAM_TOKEN` in `.env`
- Verify bot is running: `docker-compose logs bot`
- Ensure user ID is in `ALLOWED_USERS`

### Cannot connect to Sonarr/Radarr
- Verify containers are running: `docker-compose ps`
- Check API keys are correct
- Verify URLs match docker service names (e.g., `http://sonarr:8989`)

### API errors
- Check Sonarr/Radarr logs: `docker-compose logs sonarr` or `docker-compose logs radarr`
- Verify API keys have proper permissions
- Ensure root folders exist in Sonarr/Radarr configuration

## Logs

View bot logs:
```bash
docker-compose logs -f bot
```

View Sonarr logs:
```bash
docker-compose logs -f sonarr
```

View Radarr logs:
```bash
docker-compose logs -f radarr
```

## Future Enhancements

- [ ] List monitored movies/shows
- [ ] Remove/unmonitor movies/shows
- [ ] Select quality profiles and root folders
- [ ] Season selection for TV shows
- [ ] Download status notifications
- [ ] Inline query support
- [ ] Movie/show details with ratings
- [ ] Custom root folder management

## Contributing

Contributions are welcome! Feel free to submit issues and pull requests.

## License

This project is open source and available under the MIT License.

## Support

For issues, feature requests, or questions, please open an issue on the repository.
