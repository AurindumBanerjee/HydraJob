"""Unit tests for configuration, URL sanitization, and structured logging."""

import json
import logging

import pytest

from app.core.config import Settings, normalize_database_url, sanitize_database_url
from app.core.logging import JsonLogFormatter, SensitiveDataFilter


def test_settings_defaults_and_blank_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_API_KEY", "   ")
    monkeypatch.setenv("APP_ENV", "Development")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "development"
    assert settings.APP_API_KEY is None
    assert settings.TZ == "Asia/Kolkata"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.OLLAMA_BASE_URL == "http://ollama:11434"
    assert settings.OLLAMA_REQUEST_TIMEOUT == 10.0


def test_database_url_normalization_and_sanitization() -> None:
    assert (
        normalize_database_url("postgresql://user:secret@postgres:5432/hydrajob")
        == "postgresql+psycopg://user:secret@postgres:5432/hydrajob"
    )
    assert (
        normalize_database_url("postgres://user:secret@postgres:5432/hydrajob")
        == "postgresql+psycopg://user:secret@postgres:5432/hydrajob"
    )
    assert (
        sanitize_database_url("postgresql+psycopg://hydrajob:super-secret@postgres:5432/hydrajob")
        == "postgresql+psycopg://hydrajob:***@postgres:5432/hydrajob"
    )


def test_settings_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="APP_ENV"):
        Settings(_env_file=None, APP_ENV="invalid-env")

    with pytest.raises(ValueError, match="Invalid timezone"):
        Settings(_env_file=None, TZ="Mars/Olympus_Mons")

    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(_env_file=None, LOG_LEVEL="VERBOSE")


def test_structured_logging_redacts_secrets_and_db_passwords() -> None:
    secrets = ("top-secret-key", "my-api-key")
    log_filter = SensitiveDataFilter(secrets_to_mask=secrets)
    formatter = JsonLogFormatter(secrets_to_mask=secrets)

    record = logging.LogRecord(
        name="hydrajob.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=(
            "Failed connecting to "
            "postgresql+psycopg://hydrajob:dbpass123@postgres:5432/hydrajob "
            "with top-secret-key"
        ),
        args=(),
        exc_info=None,
    )
    record.api_key = "my-api-key"

    assert log_filter.filter(record) is True
    rendered = formatter.format(record)
    parsed = json.loads(rendered)

    assert "dbpass123" not in rendered
    assert "top-secret-key" not in rendered
    assert "my-api-key" not in rendered
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "hydrajob.test"
    assert parsed["context"]["api_key"] == "***"
