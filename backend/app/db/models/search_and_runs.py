"""Search configuration, ingestion run, and email message ORM models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utc_now


class JobSearch(Base, TimestampMixin):
    """Saved job discovery search criteria."""

    __tablename__ = "job_searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    locations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    remote_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employment_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    included_companies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    excluded_companies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    min_match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class IngestionRun(Base, TimestampMixin):
    """Execution audit record for URL ingestion, source scans, and search runs."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1000), index=True, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    run_type: Mapped[str] = mapped_column(String(32), default="URL_INGEST", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True, nullable=False)
    extracted_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailMessage(Base, TimestampMixin):
    """Recruitment email metadata and classification/review tracking."""

    __tablename__ = "email_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_message_id: Mapped[str] = mapped_column(
        String(200), unique=True, index=True, nullable=False
    )
    thread_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    sender_domain: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    classification: Mapped[str] = mapped_column(String(64), default="UNKNOWN", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
