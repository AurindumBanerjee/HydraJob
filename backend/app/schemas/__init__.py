"""Pydantic schemas package."""

from app.schemas.application import (
    ApplicationEventResponse,
    JobApplicationCreate,
    JobApplicationResponse,
    JobApplicationStatusUpdate,
    JobApplicationUpdate,
)
from app.schemas.common import (
    ApplicationStatus,
    ArchiveResponse,
    EligibilityStatus,
    JobStatus,
    PaginatedResponse,
    PriorityLevel,
    SourceStatus,
    TaskStatus,
)
from app.schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanySourceCreate,
    CompanySourceResponse,
    CompanySourceUpdate,
    CompanyUpdate,
)
from app.schemas.discovery import (
    DiscoveryTriggerResponse,
    IngestionRunResponse,
    JobIngestRequest,
    SourceTestResponse,
)
from app.schemas.email import (
    EmailMessageResponse,
    EmailReviewRequest,
    SyntheticEmailIngestRequest,
)
from app.schemas.job import (
    JobCreate,
    JobEvaluationResponse,
    JobResponse,
    JobSourceReferenceResponse,
    JobUpdate,
)
from app.schemas.profile import (
    ResumeCreate,
    ResumeResponse,
    ResumeUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.schemas.search import JobSearchCreate, JobSearchResponse, JobSearchUpdate
from app.schemas.system import (
    HealthResponse,
    OllamaServiceHealth,
    ReadinessResponse,
    ServiceHealth,
    SystemServicesStatus,
    SystemStatusResponse,
    TimestampInfo,
)
from app.schemas.task import TaskCreate, TaskResponse, TaskStatusUpdate, TaskUpdate

__all__ = [
    "ApplicationEventResponse",
    "ApplicationStatus",
    "ArchiveResponse",
    "CompanyCreate",
    "CompanyResponse",
    "CompanySourceCreate",
    "CompanySourceResponse",
    "CompanySourceUpdate",
    "CompanyUpdate",
    "DiscoveryTriggerResponse",
    "EligibilityStatus",
    "EmailMessageResponse",
    "EmailReviewRequest",
    "HealthResponse",
    "IngestionRunResponse",
    "JobApplicationCreate",
    "JobApplicationResponse",
    "JobApplicationStatusUpdate",
    "JobApplicationUpdate",
    "JobCreate",
    "JobEvaluationResponse",
    "JobIngestRequest",
    "JobResponse",
    "JobSearchCreate",
    "JobSearchResponse",
    "JobSearchUpdate",
    "JobSourceReferenceResponse",
    "JobStatus",
    "JobUpdate",
    "OllamaServiceHealth",
    "PaginatedResponse",
    "PriorityLevel",
    "ReadinessResponse",
    "ResumeCreate",
    "ResumeResponse",
    "ResumeUpdate",
    "ServiceHealth",
    "SourceStatus",
    "SourceTestResponse",
    "SyntheticEmailIngestRequest",
    "SystemServicesStatus",
    "SystemStatusResponse",
    "TaskCreate",
    "TaskResponse",
    "TaskStatus",
    "TaskStatusUpdate",
    "TaskUpdate",
    "TimestampInfo",
    "UserProfileResponse",
    "UserProfileUpdate",
]
