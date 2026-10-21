"""App settings, read from environment variables and the .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    APP_NAME: str = "AI Orchestrator"
    ENVIRONMENT: str = "development"

    # Required: the app will not start without these.
    DATABASE_URL: str
    GROQ_API_KEY: str

    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    CHROMA_DIR: str = "./chroma_data"

    # Comma-separated, for example "http://localhost:5173,http://localhost:3000".
    # Kept as plain text because pydantic-settings expects JSON for list fields
    # and would fail to start on a comma-separated value.
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    AGENT_MAX_RETRIES: int = 2
    AGENT_TIMEOUT_SECONDS: int = 60  # per LLM call, and for each pytest run

    # Developer <-> Critic debate loop
    DEBATE_MAX_ROUNDS: int = 3
    DEBATE_SCORE_THRESHOLD: int = 7  # critic score (1-10) that counts as good enough

    # How many times to test, fix and test again when tests fail
    RECOVERY_MAX_ATTEMPTS: int = 3

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
