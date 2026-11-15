"""Pydantic schemas for user profile and resume management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserProfileUpdate(BaseModel):
    """Payload for updating the configurable user profile."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    education: str | None = None
    degree: str | None = Field(default=None, max_length=120)
    branch: str | None = Field(default=None, max_length=120)
    university: str | None = Field(default=None, max_length=200)
    graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    cgpa: float | None = Field(default=None, ge=0.0, le=10.0)
    experience_summary: str | None = None
    projects: list[str] | None = None
    skills: list[str] | None = None
    preferred_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    excluded_locations: list[str] | None = None
    work_authorization: str | None = Field(default=None, max_length=120)


class UserProfileResponse(BaseModel):
    """Serialized user profile record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str | None = None
    education: str | None = None
    degree: str | None = None
    branch: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    cgpa: float | None = None
    experience_summary: str | None = None
    projects: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    excluded_locations: list[str] = Field(default_factory=list)
    work_authorization: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeCreate(BaseModel):
    """Payload for creating a resume version."""

    name: str = Field(min_length=1, max_length=200)
    file_path: str | None = Field(default=None, max_length=500)
    file_type: str | None = Field(default=None, max_length=50)
    extracted_text: str | None = None
    skills: list[str] = Field(default_factory=list)
    is_preferred: bool = False
    is_active: bool = True


class ResumeUpdate(BaseModel):
    """Payload for updating a resume version."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    file_path: str | None = Field(default=None, max_length=500)
    file_type: str | None = Field(default=None, max_length=50)
    extracted_text: str | None = None
    skills: list[str] | None = None
    is_preferred: bool | None = None
    is_active: bool | None = None
    is_archived: bool | None = None


class ResumeResponse(BaseModel):
    """Serialized resume version."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    file_path: str | None = None
    file_type: str | None = None
    extracted_text: str | None = None
    skills: list[str] = Field(default_factory=list)
    is_preferred: bool
    is_active: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
