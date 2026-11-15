"""Read-only Gmail adapter interface and offline synthetic inbox parser."""

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parseaddr
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.exceptions import HydraJobError

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_APP_REF_RE = re.compile(
    r"(?:application\s+(?:id|ref(?:erence)?)\s*[:#-]?\s*)?((?:APP|REQ|REF|JOB)-[A-Z0-9-]{3,20})",
    re.IGNORECASE,
)


class GmailNotConfiguredError(HydraJobError):
    """Raised when live Gmail sync is requested without OAuth credentials."""

    def __init__(self, message: str = "Gmail read-only OAuth token is not configured.") -> None:
        super().__init__(
            message,
            code="gmail_not_configured",
            status_code=503,
        )


class NormalizedEmailMessage(BaseModel):
    """Sanitized, body-free recruitment email metadata record."""

    gmail_message_id: str
    thread_id: str
    sender: str
    sender_domain: str
    subject: str
    snippet: str = Field(default="", max_length=500)
    received_at: datetime
    labels: list[str] = Field(default_factory=list)
    application_ref: str | None = None
    history_id: str | None = None


class EmailSyncCheckpoint(BaseModel):
    """Incremental synchronization checkpoint for Gmail or synthetic feeds."""

    last_history_id: str | None = None
    last_synced_at: datetime | None = None
    label_filter: str = "recruitment"
    seen_message_ids: list[str] = Field(default_factory=list)


def _extract_sender_and_domain(raw_sender: str) -> tuple[str, str]:
    display_name, email_addr = parseaddr(raw_sender or "")
    address = (email_addr or raw_sender or "").strip()
    domain = address.rsplit("@", 1)[1].lower().strip("> ") if "@" in address else ""
    safe_sender = f"{display_name} <{address}>".strip() if display_name and address else address
    return safe_sender, domain


def _parse_utc_datetime(raw_value: Any) -> datetime:
    if isinstance(raw_value, datetime):
        dt = raw_value
    elif isinstance(raw_value, (int, float)):
        ts = float(raw_value)
        if ts > 1e12:
            ts /= 1000.0
        dt = datetime.fromtimestamp(ts, tz=UTC)
    elif isinstance(raw_value, str) and raw_value.strip():
        cleaned = raw_value.strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
            ts = float(cleaned)
            if ts > 1e12:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=UTC)
        else:
            dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    else:
        return datetime.now(UTC)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _truncate_snippet(text: str, max_len: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3].rstrip() + "..."


def _detect_app_ref(subject: str, snippet: str, explicit_ref: str | None = None) -> str | None:
    if explicit_ref and explicit_ref.strip():
        return explicit_ref.strip().upper()
    match = _APP_REF_RE.search(f"{subject} {snippet}")
    return match.group(1).upper() if match else None


def parse_synthetic_messages(
    payload: str | bytes | dict[str, Any] | Sequence[dict[str, Any]],
) -> list[NormalizedEmailMessage]:
    """Parse offline synthetic JSON inbox payloads into NormalizedEmailMessage items."""
    if isinstance(payload, (str, bytes)):
        decoded = json.loads(payload)
    else:
        decoded = payload

    if isinstance(decoded, dict):
        if "messages" in decoded and isinstance(decoded["messages"], list):
            raw_items = decoded["messages"]
        else:
            raw_items = [decoded]
    elif isinstance(decoded, Sequence):
        raw_items = list(decoded)
    else:
        raise ValueError("Synthetic email payload must be a JSON object or list of objects.")

    seen_ids: set[str] = set()
    parsed: list[NormalizedEmailMessage] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        msg_id = str(item.get("gmail_message_id") or item.get("id") or "").strip()
        if not msg_id or msg_id in seen_ids:
            continue
        seen_ids.add(msg_id)

        thread_id = str(item.get("thread_id") or item.get("threadId") or msg_id).strip()
        raw_sender = str(item.get("sender") or item.get("from") or "").strip()
        safe_sender, inferred_domain = _extract_sender_and_domain(raw_sender)
        sender_domain = str(item.get("sender_domain") or inferred_domain).strip().lower()
        subject = str(item.get("subject") or "").strip()
        raw_snippet = str(item.get("snippet") or item.get("preview") or "")
        snippet = _truncate_snippet(raw_snippet)
        received_at = _parse_utc_datetime(item.get("received_at") or item.get("internalDate"))
        labels = [str(lbl).strip() for lbl in (item.get("labels") or item.get("labelIds") or [])]
        app_ref = _detect_app_ref(subject, snippet, item.get("application_ref"))
        history_id = str(item["history_id"]) if item.get("history_id") is not None else None

        parsed.append(
            NormalizedEmailMessage(
                gmail_message_id=msg_id,
                thread_id=thread_id,
                sender=safe_sender,
                sender_domain=sender_domain,
                subject=subject,
                snippet=snippet,
                received_at=received_at,
                labels=labels,
                application_ref=app_ref,
                history_id=history_id,
            )
        )

    parsed.sort(key=lambda m: m.received_at)
    return parsed


class GmailAdapter(ABC):
    """Read-only Gmail synchronization interface (never sends or deletes messages)."""

    scopes: tuple[str, ...] = (GMAIL_READONLY_SCOPE,)

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the adapter can fetch messages."""

    @abstractmethod
    async def list_messages(
        self,
        *,
        label: str = "recruitment",
        checkpoint: EmailSyncCheckpoint | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedEmailMessage], EmailSyncCheckpoint]:
        """Fetch incremental messages newer than checkpoint without modifying mailbox state."""


class SyntheticGmailAdapter(GmailAdapter):
    """Offline read-only adapter backed by synthetic JSON fixtures."""

    def __init__(self, payload: str | bytes | dict[str, Any] | Sequence[dict[str, Any]]) -> None:
        self._messages = parse_synthetic_messages(payload)

    def is_configured(self) -> bool:
        return True

    async def list_messages(
        self,
        *,
        label: str = "recruitment",
        checkpoint: EmailSyncCheckpoint | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedEmailMessage], EmailSyncCheckpoint]:
        seen = set(checkpoint.seen_message_ids) if checkpoint else set()
        cutoff = checkpoint.last_synced_at if checkpoint else None

        filtered: list[NormalizedEmailMessage] = []
        for msg in self._messages:
            if msg.gmail_message_id in seen:
                continue
            if label and msg.labels and label not in msg.labels:
                continue
            if cutoff and msg.received_at < cutoff:
                continue
            filtered.append(msg)
            if len(filtered) >= max_results:
                break

        updated_seen = list(dict.fromkeys([*seen, *(m.gmail_message_id for m in filtered)]))
        newest_dt = max((m.received_at for m in filtered), default=cutoff)
        newest_history = next(
            (m.history_id for m in reversed(filtered) if m.history_id),
            checkpoint.last_history_id if checkpoint else None,
        )
        new_checkpoint = EmailSyncCheckpoint(
            last_history_id=newest_history,
            last_synced_at=newest_dt,
            label_filter=label,
            seen_message_ids=updated_seen,
        )
        return filtered, new_checkpoint


class ReadOnlyGmailApiAdapter(GmailAdapter):
    """Read-only Gmail REST API client using OAuth bearer token (metadata + snippet only)."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str = "https://gmail.googleapis.com/gmail/v1",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._access_token = (access_token or "").strip() or None
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._external_client = client

    def is_configured(self) -> bool:
        return self._access_token is not None

    async def list_messages(
        self,
        *,
        label: str = "recruitment",
        checkpoint: EmailSyncCheckpoint | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedEmailMessage], EmailSyncCheckpoint]:
        if not self._access_token:
            raise GmailNotConfiguredError()

        headers = {"Authorization": f"Bearer {self._access_token}"}
        params: dict[str, Any] = {"maxResults": max_results}
        if label:
            params["q"] = f"label:{label}"

        seen = set(checkpoint.seen_message_ids) if checkpoint else set()
        owns_client = self._external_client is None
        http_client = self._external_client or httpx.AsyncClient(timeout=self.timeout)
        try:
            list_resp = await http_client.get(
                f"{self.base_url}/users/me/messages",
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            list_resp.raise_for_status()
            list_data = list_resp.json()
            raw_refs = list_data.get("messages", []) if isinstance(list_data, dict) else []

            messages: list[NormalizedEmailMessage] = []
            for ref in raw_refs:
                msg_id = str(ref.get("id") or "").strip()
                if not msg_id or msg_id in seen:
                    continue
                detail_resp = await http_client.get(
                    f"{self.base_url}/users/me/messages/{msg_id}",
                    headers=headers,
                    params=[
                        ("format", "metadata"),
                        ("metadataHeaders", "From"),
                        ("metadataHeaders", "Subject"),
                        ("metadataHeaders", "Date"),
                    ],
                    timeout=self.timeout,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()
                headers_list = detail.get("payload", {}).get("headers", [])
                header_map = {
                    str(h.get("name", "")).lower(): str(h.get("value", ""))
                    for h in headers_list
                    if isinstance(h, dict)
                }
                safe_sender, sender_domain = _extract_sender_and_domain(header_map.get("from", ""))
                subject = header_map.get("subject", "").strip()
                snippet = _truncate_snippet(str(detail.get("snippet") or ""))
                received_at = _parse_utc_datetime(detail.get("internalDate"))

                messages.append(
                    NormalizedEmailMessage(
                        gmail_message_id=msg_id,
                        thread_id=str(detail.get("threadId") or msg_id),
                        sender=safe_sender,
                        sender_domain=sender_domain,
                        subject=subject,
                        snippet=snippet,
                        received_at=received_at,
                        labels=list(detail.get("labelIds") or []),
                        application_ref=_detect_app_ref(subject, snippet),
                        history_id=str(detail["historyId"]) if detail.get("historyId") else None,
                    )
                )

            messages.sort(key=lambda m: m.received_at)
            updated_seen = list(dict.fromkeys([*seen, *(m.gmail_message_id for m in messages)]))
            newest_dt = max(
                (m.received_at for m in messages),
                default=(checkpoint.last_synced_at if checkpoint else None),
            )
            newest_history = next(
                (m.history_id for m in reversed(messages) if m.history_id),
                checkpoint.last_history_id if checkpoint else None,
            )
            return messages, EmailSyncCheckpoint(
                last_history_id=newest_history,
                last_synced_at=newest_dt,
                label_filter=label,
                seen_message_ids=updated_seen,
            )
        finally:
            if owns_client:
                await http_client.aclose()
