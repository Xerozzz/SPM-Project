"""Application settings, read from the environment.

Twelve-factor: configuration comes from the environment, never from a committed file.
`.env.example` documents every variable; `.env` is gitignored.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for one running instance of the API.

    Field names map to upper-case environment variables (`database_url` -> `DATABASE_URL`).
    Secrets deliberately have no default: the API fails to start rather than run on a
    well-known signing key.
    """

    # env_file is resolved from the working directory, so this reads api/.env when you
    # run the API directly on your machine. Under Docker Compose there is no such file:
    # Compose injects the values from the repository-root .env as real env vars.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_expiry_minutes: int = 60
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS as a list. It arrives as a comma-separated string from the env."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; the cache makes this safe to call anywhere."""
    return Settings()
