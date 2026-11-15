"""Pydantic schemas for jobs, source references, and evaluations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import JobStatus


class JobCreate(BaseModel):
    """Payload for manually creating a job record."""

    company_id: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=120)
    employment_type: str | None = Field(default=None, max_length=80)
    workplace_type: str | None = Field(default=None, max_length=80)
    experience_requirement: str | None = Field(default=None, max_length=200)
    graduation_year_requirement: int | None = Field(default=None, ge=1990, le=2100)
    degree_requirement: str | None = Field(default=None, max_length=200)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    salary: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=16)
    application_deadline: datetime | None = None
    application_url: str | None = Field(default=None, max_length=1000)
    canonical_url: str | None = Field(default=None, max_length=1000)
    external_job_id: str | None = Field(default=None, max_length=200)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_extraction_data: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.ACTIVE
    is_active: bool = True


class JobUpdate(BaseModel):
    """Payload for updating a job record."""

    company_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=120)
    employment_type: str | None = Field(default=None, max_length=80)
    workplace_type: str | None = Field(default=None, max_length=80)
    experience_requirement: str | None = Field(default=None, max_length=200)
    graduation_year_requirement: int | None = Field(default=None, ge=1990, le=2100)
    degree_requirement: str | None = Field(default=None, max_length=200)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    responsibilities: list[str] | None = None
    qualifications: list[str] | None = None
    salary: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=16)
    application_deadline: datetime | None = None
    application_url: str | None = Field(default=None, max_length=1000)
    canonical_url: str | None = Field(default=None, max_length=1000)
    external_job_id: str | None = Field(default=None, max_length=200)
    source_metadata: dict[str, Any] | None = None
    raw_extraction_data: dict[str, Any] | None = None
    status: JobStatus | None = None
    is_active: bool | None = None
    is_archived: bool | None = None


class JobSourceReferenceResponse(BaseModel):
    """Serialized job source reference."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    source_id: UUID | None = None
    source_external_id: str | None = None
    original_url: str
    canonical_url: str
    first_seen_at: datetime
    last_seen_at: datetime


class JobEvaluateRequest(BaseModel):
    """Optional request payload for evaluating a job against the user profile."""

    resume_id: UUID | None = None
    use_ollama: bool = False


class JobEvaluationResponse(BaseModel):
    """Serialized job evaluation snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    profile_id: UUID | None = None
    recommended_resume_id: UUID | None = None
    eligibility_status: str
    overall_score: int
    component_scores: dict[str, float] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendation: str
    explanation: str
    model_name: str
    evaluation_version: str
    evaluated_at: datetime


class JobResponse(BaseModel):
    """Serialized job record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    title: str
    normalized_title: str
    description: str | None = None
    location: str | None = None
    normalized_location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    experience_requirement: str | None = None
    graduation_year_requirement: int | None = None
    degree_requirement: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    salary: str | None = None
    currency: str | None = None
    application_deadline: datetime | None = None
    application_url: str | None = None
    canonical_url: str | None = None
    external_job_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_extraction_data: dict[str, Any] = Field(default_factory=dict)
    status: str
    is_active: bool
    is_archived: bool
    missing_scan_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    last_changed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
