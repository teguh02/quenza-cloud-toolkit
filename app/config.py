"""Application configuration loaded from environment variables (.env).

Uses pydantic-settings for validation so the app fails fast with a clear
message when required values are missing or malformed.
"""

from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values are read from the environment and/or a local `.env` file.
    """

    # Authentication
    master_password_hash: str = Field(
        default="",
        alias="MASTER_PASSWORD_HASH",
        description="Bcrypt hash of the Master Password.",
    )

    # Session
    secret_key: str = Field(
        default="change-me",
        alias="SECRET_KEY",
        description="Secret used to sign session cookies.",
    )
    session_max_age: int = Field(
        default=28800,
        alias="SESSION_MAX_AGE",
        description="Session lifetime in seconds.",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///./quenza.db",
        alias="DATABASE_URL",
        description="SQLAlchemy database URL.",
    )

    # Backup engine (Phase 4)
    backup_work_dir: str = Field(
        default="./backups",
        alias="BACKUP_WORK_DIR",
        description="Directory for staging/local backup output.",
    )
    mysqldump_path: str = Field(
        default="mysqldump",
        alias="MYSQLDUMP_PATH",
        description="Path to the mysqldump executable.",
    )
    pg_dump_path: str = Field(
        default="pg_dump",
        alias="PG_DUMP_PATH",
        description="Path to the pg_dump executable.",
    )

    # Application
    debug: bool = Field(
        default=True,
        alias="DEBUG",
        description="Enable debug mode (relaxes cookie security).",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_configured(self) -> bool:
        """True when the minimum required secrets are present."""
        return bool(self.master_password_hash) and self.secret_key != "change-me"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Raises:
        RuntimeError: if the environment cannot be parsed into Settings.
    """
    try:
        return Settings()
    except ValidationError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            "Failed to load configuration from environment/.env:\n"
            f"{exc}"
        ) from exc


# Module-level singleton for convenient imports.
settings = get_settings()
