from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    telegram_token: str
    sonarr_url: str
    sonarr_api_key: str
    radarr_url: str
    radarr_api_key: str
    allowed_users: str  # Comma-separated list of user IDs
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse allowed users from comma-separated string."""
        return [int(uid.strip()) for uid in self.allowed_users.split(",") if uid.strip()]


settings = Settings()
