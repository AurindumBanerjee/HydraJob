"""Job, source-reference, and evaluation ORM models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.application import JobApplication
    from app.db.models.company import Company


class Job(Base, TimestampMixin):
    """Canonical job opening record."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    normalized_location: Mapped[str | None] = mapped_column(
        String(200), index=True, nullable=True
    )
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    experience_requirement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    degree_requirement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    qualifications: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    salary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    application_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(
        String(1000), unique=True, index=True, nullable=True
    )
    external_job_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_extraction_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missing_scan_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company: Mapped["Company"] = relationship(back_populates="jobs")
    source_references: Mapped[list["JobSourceReference"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list["JobEvaluation"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["JobApplication"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class JobSourceReference(Base, TimestampMixin):
    """Source URL / external ID provenance preserved across deduplication."""

    __tablename__ = "job_source_references"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    original_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), index=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="source_references")


class JobEvaluation(Base, TimestampMixin):
    """Profile matching and eligibility evaluation snapshot for a job."""

    __tablename__ = "job_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommended_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resumes.id", ondelete="SET NULL"),
        nullable=True,
    )
    eligibility_status: Mapped[str] = mapped_column(
        String(32), default="NOT_EVALUATED", nullable=False
    )
    overall_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    component_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    concerns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(64), default="REVIEW", nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    evaluation_version: Mapped[str] = mapped_column(String(32), default="v1.0", nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="evaluations")
