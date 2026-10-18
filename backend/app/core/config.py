"""Application settings, read from the environment (and `.env` for local runs)."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "dev"
    log_level: str = "INFO"

    # PostgreSQL: either DATABASE_URL, or the POSTGRES_* variables shared with docker-compose.
    database_url: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # MongoDB buffer for unconfirmed meal recognitions (DB-02): MONGO_URL, or MONGO_INITDB_ROOT_* shared with compose.
    mongo_url: str | None = None
    mongo_initdb_root_username: str | None = None
    mongo_initdb_root_password: str | None = None
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "fitplan"
    recognition_ttl_hours: int = Field(default=6, ge=1)

    # Directory of the stored meal photos (`meals/<user id>/...`); None = photos are not stored (yet).
    photo_dir: str | None = None

    # Auth (FR-U2, decision D4). The secret has no default: the app refuses to start without it.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)

    # Per client IP and route, sliding window (B-02). Final numbers belong to D-06.
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60

    # Hardening and capacity (B-29). See backend/README.md for how the numbers add up.
    # Connection pool of ONE worker process: at most db_pool_size + db_max_overflow connections to PostgreSQL.
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: float = Field(default=10, gt=0)  # waiting for a free connection, then 503
    db_pool_recycle_seconds: int = Field(default=1800, ge=-1)
    # Request body limits in bytes; the photo upload (POST /meals/recognitions) has its own, larger limit.
    max_body_bytes: int = Field(default=1024 * 1024, ge=1024)
    max_upload_bytes: int = Field(default=9 * 1024 * 1024, ge=1024)
    # Comma separated origins allowed by CORS (the mobile app does not need CORS; this is for a web client or tools).
    cors_origins: str = ""
    # Strict-Transport-Security max-age in seconds; 0 = do not send (set it only behind HTTPS).
    hsts_max_age_seconds: int = Field(default=0, ge=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_database_url(self) -> str | None:
        if self.database_url:
            return self.database_url
        if self.postgres_user and self.postgres_password and self.postgres_db:
            return (f"postgresql+asyncpg://{quote(self.postgres_user)}:{quote(self.postgres_password)}"
                    f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")
        return None

    @property
    def resolved_mongo_url(self) -> str | None:
        if self.mongo_url:
            return self.mongo_url
        if self.mongo_initdb_root_username and self.mongo_initdb_root_password:
            return (f"mongodb://{quote(self.mongo_initdb_root_username)}:{quote(self.mongo_initdb_root_password)}"
                    f"@{self.mongo_host}:{self.mongo_port}/?authSource=admin")
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
