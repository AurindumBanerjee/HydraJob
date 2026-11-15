"""Structured JSON logging with secret redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

_URL_CREDENTIALS_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+:)([^@\s]+)(@)")
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def redact_sensitive_text(text: str, secrets_to_mask: tuple[str, ...] = ()) -> str:
    """Mask URL passwords and configured secret values in log strings."""
    masked = _URL_CREDENTIALS_RE.sub(r"\1***\3", text)
    for secret in secrets_to_mask:
        if secret:
            masked = masked.replace(secret, "***")
    return masked


class SensitiveDataFilter(logging.Filter):
    """Logging filter that strips secrets and DB credentials from records."""

    def __init__(self, secrets_to_mask: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets_to_mask if s)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_sensitive_text(value, self._secrets)
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items()}
        if isinstance(value, tuple):
            return tuple(self._redact(v) for v in value)
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg, self._secrets)
        if record.args:
            record.args = self._redact(record.args)
        for key, value in list(record.__dict__.items()):
            if key not in _RESERVED_RECORD_ATTRS and isinstance(value, (str, dict, list, tuple)):
                record.__dict__[key] = self._redact(value)
        return True


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def __init__(self, secrets_to_mask: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets_to_mask if s)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage(), self._secrets),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            payload["context"] = extras

        if record.exc_info:
            payload["exception"] = redact_sensitive_text(
                self.formatException(record.exc_info),
                self._secrets,
            )

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", settings: Settings | None = None) -> None:
    """Configure root and application loggers for structured JSON output."""
    secrets_to_mask: tuple[str, ...] = ()
    if settings is not None:
        secrets_to_mask = tuple(
            s for s in (settings.APP_SECRET_KEY, settings.APP_API_KEY or "") if s
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(secrets_to_mask=secrets_to_mask))
    handler.addFilter(SensitiveDataFilter(secrets_to_mask=secrets_to_mask))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
