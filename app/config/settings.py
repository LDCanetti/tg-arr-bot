from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    telegram_token: str
    sonarr_url: str
    sonarr_api_key: str
    radarr_url: str
    radarr_api_key: str
    allowed_users: str  # Comma-separated list of user IDs
    # Comma-separated chat IDs (negative, e.g. -1001234567890) whose members may all
    # use the bot. Anyone added to such a group gets library write access.
    allowed_chats: str = ""

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

    # After an update with new release notes, privately message ALLOWED_USERS
    # the notes once. Set false to keep quiet.
    update_notices: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse allowed users from comma-separated string.

        Negative IDs are chat IDs, not user IDs — they can never match a user and
        belong in ALLOWED_CHATS, so drop them here rather than silently never matching.
        """
        ids = [int(uid.strip()) for uid in self.allowed_users.split(",") if uid.strip()]
        return [uid for uid in ids if uid > 0]

    @property
    def allowed_chat_ids(self) -> list[int]:
        """Parse allowed group chats from comma-separated string."""
        return [int(cid.strip()) for cid in self.allowed_chats.split(",") if cid.strip()]


settings = Settings()
