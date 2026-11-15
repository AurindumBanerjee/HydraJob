"""Pydantic schemas for companies and career-page sources."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SourceStatus


class CompanyCreate(BaseModel):
    """Payload for creating a tracked company."""

    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    description: str | None = None
    notes: str | None = None


class CompanyUpdate(BaseModel):
    """Payload for updating a tracked company."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    description: str | None = None
    notes: str | None = None
    is_archived: bool | None = None


class CompanyResponse(BaseModel):
    """Serialized company record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    normalized_name: str
    website: str | None = None
    industry: str | None = None
    description: str | None = None
    notes: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CompanySourceCreate(BaseModel):
    """Payload for registering a career-page source."""

    company_id: UUID
    source_name: str = Field(min_length=1, max_length=200)
    career_url: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="career_page", max_length=64)
    extraction_method: str = Field(default="auto", max_length=64)
    adapter_name: str = Field(default="generic_html", max_length=64)
    status: SourceStatus = SourceStatus.NEEDS_CONFIGURATION
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class CompanySourceUpdate(BaseModel):
    """Payload for updating a career-page source."""

    source_name: str | None = Field(default=None, min_length=1, max_length=200)
    career_url: str | None = Field(default=None, min_length=1, max_length=1000)
    source_type: str | None = Field(default=None, max_length=64)
    extraction_method: str | None = Field(default=None, max_length=64)
    adapter_name: str | None = Field(default=None, max_length=64)
    status: SourceStatus | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None
    is_archived: bool | None = None


class CompanySourceResponse(BaseModel):
    """Serialized career-page source record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    source_name: str
    career_url: str
    canonical_url: str
    source_type: str
    extraction_method: str
    adapter_name: str
    status: str
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    is_archived: bool
    consecutive_failures: int
    last_checked_at: datetime | None = None
    last_successful_scan_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
