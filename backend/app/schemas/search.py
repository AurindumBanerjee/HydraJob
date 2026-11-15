"""Pydantic schemas for saved job search configurations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobSearchCreate(BaseModel):
    """Payload for creating a job search configuration."""

    name: str = Field(min_length=1, max_length=200)
    keywords: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = Field(default=None, max_length=64)
    employment_types: list[str] = Field(default_factory=list)
    graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    experience_level: str | None = Field(default=None, max_length=64)
    included_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class JobSearchUpdate(BaseModel):
    """Payload for updating a job search configuration."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    keywords: list[str] | None = None
    roles: list[str] | None = None
    categories: list[str] | None = None
    locations: list[str] | None = None
    remote_preference: str | None = Field(default=None, max_length=64)
    employment_types: list[str] | None = None
    graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    experience_level: str | None = Field(default=None, max_length=64)
    included_companies: list[str] | None = None
    excluded_companies: list[str] | None = None
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    filters: dict[str, Any] | None = None
    is_active: bool | None = None
    is_archived: bool | None = None


class JobSearchResponse(BaseModel):
    """Serialized job search configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    keywords: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = None
    employment_types: list[str] = Field(default_factory=list)
    graduation_year: int | None = None
    experience_level: str | None = None
    included_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    min_match_score: int | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
