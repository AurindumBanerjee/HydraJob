"""Application configuration loaded from environment variables."""

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_APP_ENVS = frozenset({"development", "test", "staging", "production"})
ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
DEFAULT_DATABASE_URL = "postgresql+psycopg://hydrajob:hydrajob@postgres:5432/hydrajob"


def normalize_database_url(url: str) -> str:
    """Ensure PostgreSQL URLs default to the psycopg (v3) SQLAlchemy driver."""
    cleaned = url.strip()
    if not cleaned:
        return DEFAULT_DATABASE_URL
    if cleaned.startswith("postgres://"):
        return "postgresql+psycopg://" + cleaned[len("postgres://") :]
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    return cleaned


def sanitize_database_url(url: str) -> str:
    """Return a database URL with any embedded password masked."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-database-url>"

    if parts.password is None:
        return url

    username = parts.username or ""
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{username}:***@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Settings(BaseSettings):
    """Typed runtime settings for the HydraJob backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "HydraJob"
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = Field(default="", repr=False)
    APP_API_KEY: str | None = Field(default=None, repr=False)

    DATABASE_URL: str = Field(default=DEFAULT_DATABASE_URL, repr=False)

    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = ""
    OLLAMA_REQUEST_TIMEOUT: float = Field(default=10.0, gt=0)

    TZ: str = "Asia/Kolkata"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def _validate_app_env(cls, value: object) -> str:
        env = str(value or "development").strip().lower()
        if env not in ALLOWED_APP_ENVS:
            allowed = ", ".join(sorted(ALLOWED_APP_ENVS))
            raise ValueError(f"APP_ENV must be one of: {allowed}")
        return env

    @field_validator("APP_API_KEY", mode="before")
    @classmethod
    def _normalize_optional_api_key(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _validate_database_url(cls, value: object) -> str:
        if value is None:
            return DEFAULT_DATABASE_URL
        cleaned = str(value).strip()
        return cleaned or DEFAULT_DATABASE_URL

    @field_validator("OLLAMA_BASE_URL", mode="before")
    @classmethod
    def _normalize_ollama_url(cls, value: object) -> str:
        cleaned = str(value or "http://ollama:11434").strip()
        return cleaned.rstrip("/") or "http://ollama:11434"

    @field_validator("OLLAMA_MODEL", mode="before")
    @classmethod
    def _normalize_ollama_model(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("TZ", mode="before")
    @classmethod
    def _validate_timezone(cls, value: object) -> str:
        tz_name = str(value or "Asia/Kolkata").strip() or "Asia/Kolkata"
        try:
            ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid timezone: {tz_name}") from exc
        return tz_name

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _validate_log_level(cls, value: object) -> str:
        level = str(value or "INFO").strip().upper()
        if level not in ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return level

    @property
    def sqlalchemy_database_url(self) -> str:
        """Database URL normalized for SQLAlchemy 2.x."""
        return normalize_database_url(self.DATABASE_URL)

    @property
    def sanitized_database_url(self) -> str:
        """Database URL with credentials masked for safe diagnostics."""
        return sanitize_database_url(self.sqlalchemy_database_url)

    @property
    def is_development(self) -> bool:
        """Return True when running in local development or test mode."""
        return self.APP_ENV in {"development", "test"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
