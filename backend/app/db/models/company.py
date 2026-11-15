"""Company and career-page source ORM models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.job import Job


class Company(Base, TimestampMixin):
    """Tracked employer or organization."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(200), unique=True, index=True, nullable=False
    )
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sources: Mapped[list["CompanySource"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )


class CompanySource(Base, TimestampMixin):
    """Registered company career page or public job-board feed."""

    __tablename__ = "company_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    career_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(
        String(1000), unique=True, index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), default="career_page", nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), default="auto", nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(64), default="generic_html", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="NEEDS_CONFIGURATION", nullable=False
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_successful_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped[Company] = relationship(back_populates="sources")
