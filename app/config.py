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

    # Secrets encryption (Fernet). Used to encrypt sensitive destination
    # config such as Google Drive refresh tokens.
    encryption_key: str = Field(
        default="",
        alias="ENCRYPTION_KEY",
        description="Fernet key (urlsafe base64) for encrypting secrets.",
    )

    # Google Drive OAuth (Phase 4.5)
    google_client_id: str = Field(
        default="",
        alias="GOOGLE_CLIENT_ID",
        description="Google OAuth client ID.",
    )
    google_client_secret: str = Field(
        default="",
        alias="GOOGLE_CLIENT_SECRET",
        description="Google OAuth client secret.",
    )
    google_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/destinations/gdrive/callback",
        alias="GOOGLE_REDIRECT_URI",
        description="OAuth redirect URI registered in Google Cloud Console.",
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

    @property
    def google_oauth_ready(self) -> bool:
        """True when Google Drive OAuth is fully configured."""
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_redirect_uri
        )


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
