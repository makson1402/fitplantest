"""Application settings, read from the environment (and `.env` for local runs)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "dev"
    log_level: str = "INFO"

    # Auth (FR-U2, decision D4). The secret has no default: the app refuses to start without it.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)

    # Per client IP and route, sliding window (B-02). Final numbers belong to D-06.
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
