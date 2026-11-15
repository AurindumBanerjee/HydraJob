"""Shared Pydantic schemas, enums, and pagination envelopes."""

from enum import StrEnum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApplicationStatus(StrEnum):
    """Supported 16-stage job application lifecycle statuses."""

    DISCOVERED = "DISCOVERED"
    TO_APPLY = "TO_APPLY"
    PREPARING = "PREPARING"
    APPLIED = "APPLIED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNDER_REVIEW = "UNDER_REVIEW"
    OA_RECEIVED = "OA_RECEIVED"
    OA_COMPLETED = "OA_COMPLETED"
    TECHNICAL_TEST = "TECHNICAL_TEST"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    FURTHER_ROUNDS = "FURTHER_ROUNDS"
    OFFER_RECEIVED = "OFFER_RECEIVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class TaskStatus(StrEnum):
    """Internal task lifecycle statuses."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PriorityLevel(StrEnum):
    """Task and application priority levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class SourceStatus(StrEnum):
    """Career source onboarding and operational statuses."""

    READY = "READY"
    NEEDS_CONFIGURATION = "NEEDS_CONFIGURATION"
    DISABLED = "DISABLED"


class JobStatus(StrEnum):
    """Canonical job opening lifecycle statuses."""

    ACTIVE = "ACTIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class EligibilityStatus(StrEnum):
    """Mandatory eligibility assessment outcomes."""

    ELIGIBLE = "ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    INELIGIBLE = "INELIGIBLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list envelope."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ArchiveResponse(BaseModel):
    """Result of soft-archiving a resource."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_archived: bool
    message: str
