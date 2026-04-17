from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    AGENT_API_KEY: str = "secret-key-123"

    # Limits
    RATE_LIMIT_PER_MINUTE: int = 10
    MONTHLY_BUDGET_USD: float = 10.0

    # Conversation
    HISTORY_LIMIT: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()