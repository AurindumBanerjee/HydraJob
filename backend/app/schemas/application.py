"""Pydantic schemas for job applications and immutable event history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ApplicationStatus, EligibilityStatus, PriorityLevel


class JobApplicationCreate(BaseModel):
    """Payload for creating a tracked job application."""

    job_id: UUID
    selected_resume_id: UUID | None = None
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    priority: PriorityLevel = PriorityLevel.MEDIUM
    match_score: int | None = Field(default=None, ge=0, le=100)
    eligibility_status: EligibilityStatus | None = None
    application_date: datetime | None = None
    notes: str | None = None
    thread_id: str | None = Field(default=None, max_length=200)


class JobApplicationUpdate(BaseModel):
    """Payload for updating application metadata."""

    selected_resume_id: UUID | None = None
    priority: PriorityLevel | None = None
    match_score: int | None = Field(default=None, ge=0, le=100)
    eligibility_status: EligibilityStatus | None = None
    application_date: datetime | None = None
    notes: str | None = None
    thread_id: str | None = Field(default=None, max_length=200)
    is_archived: bool | None = None


class JobApplicationStatusUpdate(BaseModel):
    """Payload for transitioning an application status with audit history."""

    status: ApplicationStatus
    notes: str | None = None
    description: str | None = None
    source: str = Field(default="manual", max_length=64)
    application_date: datetime | None = None


class ApplicationEventResponse(BaseModel):
    """Serialized immutable application audit event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    event_type: str
    previous_status: str | None = None
    new_status: str | None = None
    source: str
    description: str | None = None
    confidence: float | None = None
    needs_review: bool
    email_message_id: UUID | None = None
    occurred_at: datetime


class JobApplicationResponse(BaseModel):
    """Serialized job application record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    selected_resume_id: UUID | None = None
    status: str
    priority: str
    match_score: int | None = None
    eligibility_status: str | None = None
    application_date: datetime | None = None
    notes: str | None = None
    thread_id: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
