"""Pydantic schemas for URL ingestion, source onboarding, and discovery runs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobIngestRequest(BaseModel):
    """Payload for submitting an individual job URL for ingestion."""

    url: str = Field(min_length=1, max_length=1000)
    company_id: UUID | None = None
    source_id: UUID | None = None
    use_ollama: bool = True
    html_content: str | None = None
    raw_payload: dict[str, Any] | list[Any] | None = None


class SourceRegisterRequest(BaseModel):
    """Payload for onboarding and auto-inspecting a career-page source."""

    company_id: UUID | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    source_name: str | None = Field(default=None, min_length=1, max_length=200)
    career_url: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="career_page", max_length=64)
    sample_content: str | None = None


class SourceContentRequest(BaseModel):
    """Optional inline fixture payload for testing or scanning a source offline."""

    sample_content: str | None = None


class IngestionRunResponse(BaseModel):
    """Serialized ingestion or discovery run record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str | None = None
    canonical_url: str | None = None
    source_id: UUID | None = None
    run_type: str
    status: str
    extracted_job_id: UUID | None = None
    jobs_discovered: int
    jobs_new: int
    jobs_updated: int
    errors: list[str] = Field(default_factory=list)
    retry_count: int
    max_retries: int
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SourceTestResponse(BaseModel):
    """Result of testing a career-page source configuration."""

    source_id: UUID
    adapter_name: str
    detected_ats: str | None = None
    status: str
    sample_jobs: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DiscoveryTriggerResponse(BaseModel):
    """Summary response for triggered source or search discovery runs."""

    runs: list[IngestionRunResponse] = Field(default_factory=list)
    total_discovered: int = 0
    total_new: int = 0
    total_updated: int = 0
