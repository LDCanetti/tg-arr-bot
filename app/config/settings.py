from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    telegram_token: str
    sonarr_url: str
    sonarr_api_key: str
    radarr_url: str
    radarr_api_key: str
    allowed_users: str  # Comma-separated list of user IDs

    # Root folder paths — must match a registered root folder in Sonarr/Radarr.
    # Defaults target the single-mount /data layout; override via env if yours differ.
    sonarr_root_shows: str = "/data/Plex/Shows"
    sonarr_root_anime: str = "/data/Plex/Anime"
    radarr_root_movies: str = "/data/Plex/Movies"

    # Quality profile applied to everything the bot adds. 1 is "Any" — grab any
    # quality, then upgrade toward the profile cutoff. Must exist in Sonarr/Radarr.
    quality_profile_id: int = 1

    # Logging verbosity (DEBUG, INFO, WARNING, ERROR). DEBUG logs message contents.
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse allowed users from comma-separated string."""
        return [int(uid.strip()) for uid in self.allowed_users.split(",") if uid.strip()]


settings = Settings()
