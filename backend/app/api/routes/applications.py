"""Job application tracking and immutable event history API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.application import (
    ApplicationEventResponse,
    JobApplicationCreate,
    JobApplicationResponse,
    JobApplicationStatusUpdate,
    JobApplicationUpdate,
)
from app.schemas.common import ApplicationStatus, ArchiveResponse, PaginatedResponse, PriorityLevel

router = APIRouter(
    prefix="/applications",
    tags=["applications"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=PaginatedResponse[JobApplicationResponse])
def list_applications(
    db: Annotated[Session, Depends(get_db)],
    job_id: UUID | None = None,
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    priority: PriorityLevel | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobApplicationResponse]:
    """List tracked job applications with filtering and pagination."""
    items, total = crud.list_applications(
        db,
        job_id=job_id,
        status_filter=status_filter.value if status_filter else None,
        priority=priority.value if priority else None,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[JobApplicationResponse](
        items=[JobApplicationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=JobApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: JobApplicationCreate,
    db: Annotated[Session, Depends(get_db)],
) -> JobApplicationResponse:
    """Create a job application and record its initial audit event."""
    application = crud.create_application(db, payload)
    return JobApplicationResponse.model_validate(application)


@router.get("/{application_id}", response_model=JobApplicationResponse)
def get_application(
    application_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> JobApplicationResponse:
    """Retrieve a job application by ID."""
    application = crud.get_application(db, application_id)
    return JobApplicationResponse.model_validate(application)


@router.put("/{application_id}", response_model=JobApplicationResponse)
def update_application(
    application_id: UUID,
    payload: JobApplicationUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> JobApplicationResponse:
    """Update non-status metadata on a job application."""
    application = crud.update_application(db, application_id, payload)
    return JobApplicationResponse.model_validate(application)


@router.patch("/{application_id}/status", response_model=JobApplicationResponse)
def update_application_status(
    application_id: UUID,
    payload: JobApplicationStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> JobApplicationResponse:
    """Transition application status and append an immutable ApplicationEvent."""
    application = crud.update_application_status(db, application_id, payload)
    return JobApplicationResponse.model_validate(application)


@router.get("/{application_id}/events", response_model=PaginatedResponse[ApplicationEventResponse])
def list_application_events(
    application_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[ApplicationEventResponse]:
    """List immutable chronological audit events for an application."""
    items, total = crud.list_application_events(
        db,
        application_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[ApplicationEventResponse](
        items=[ApplicationEventResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{application_id}", response_model=ArchiveResponse)
def archive_application(
    application_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive an application while preserving its historical events."""
    application = crud.archive_application(db, application_id)
    return ArchiveResponse(
        id=application.id,
        is_archived=application.is_archived,
        message="Application archived.",
    )
