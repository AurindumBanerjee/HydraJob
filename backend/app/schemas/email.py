"""Pydantic schemas for recruitment email tracking and review."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SyntheticEmailIngestRequest(BaseModel):
    """Payload for ingesting a synthetic or parsed recruitment message."""

    gmail_message_id: str = Field(min_length=1, max_length=200)
    thread_id: str | None = Field(default=None, max_length=200)
    sender: str = Field(min_length=1, max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    snippet: str | None = None
    body: str | None = None
    received_at: datetime | None = None


class EmailReviewRequest(BaseModel):
    """Payload for manually reviewing and linking a recruitment email."""

    classification: str | None = Field(default=None, max_length=64)
    matched_application_id: UUID | None = None
    apply_status_update: bool = False
    needs_review: bool = False
    review_notes: str | None = None


class EmailSyncRequest(BaseModel):
    """Payload for syncing synthetic recruitment messages in batch."""

    messages: list[SyntheticEmailIngestRequest] = Field(default_factory=list)
    use_ollama: bool = False


class EmailMessageResponse(BaseModel):
    """Serialized recruitment email record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gmail_message_id: str
    thread_id: str | None = None
    sender: str
    sender_domain: str | None = None
    subject: str
    snippet: str | None = None
    received_at: datetime
    classification: str
    confidence: float | None = None
    matched_application_id: UUID | None = None
    status_applied: bool
    needs_review: bool
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime
