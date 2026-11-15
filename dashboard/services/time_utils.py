"""Timezone helpers ensuring user-facing timestamps display in Asia/Kolkata."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

IST_ZONE = ZoneInfo("Asia/Kolkata")
IST_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S IST"


def now_kolkata() -> datetime:
    """Return the current timezone-aware datetime in Asia/Kolkata."""
    return datetime.now(UTC).astimezone(IST_ZONE)


def now_kolkata_iso() -> str:
    """Return the current timestamp in Asia/Kolkata as an ISO-8601 string."""
    return now_kolkata().isoformat(timespec="seconds")


def now_kolkata_formatted() -> str:
    """Return the current timestamp formatted cleanly for Asia/Kolkata display."""
    return now_kolkata().strftime(IST_DISPLAY_FORMAT)


def format_kolkata_timestamp(value: str | datetime | None) -> str:
    """Parse an ISO timestamp or datetime and format it in Asia/Kolkata.

    Returns ``"Unavailable"`` for empty inputs and falls back to the raw string
    if an unparseable value is provided.
    """
    if value is None:
        return "Unavailable"

    if isinstance(value, datetime):
        dt = value
    else:
        raw = value.strip()
        if not raw:
            return "Unavailable"
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return raw

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(IST_ZONE).strftime(IST_DISPLAY_FORMAT)
