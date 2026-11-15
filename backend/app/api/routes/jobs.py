"""Job opening CRUD API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.common import ArchiveResponse, JobStatus, PaginatedResponse
from app.schemas.job import JobCreate, JobResponse, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=PaginatedResponse[JobResponse])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    company_id: UUID | None = None,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    is_active: bool | None = None,
    include_archived: bool = False,
    search: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobResponse]:
    """List jobs with filtering, sorting, and pagination."""
    items, total = crud.list_jobs(
        db,
        company_id=company_id,
        status_filter=status_filter.value if status_filter else None,
        is_active=is_active,
        include_archived=include_archived,
        search=search,
        location=location,
        employment_type=employment_type,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[JobResponse](
        items=[JobResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Create a job record manually."""
    job = crud.create_job(db, payload)
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Retrieve a single job by ID."""
    job = crud.get_job(db, job_id)
    return JobResponse.model_validate(job)


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    payload: JobUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Update a job record."""
    job = crud.update_job(db, job_id, payload)
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", response_model=ArchiveResponse)
def archive_job(
    job_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive a job record."""
    job = crud.archive_job(db, job_id)
    return ArchiveResponse(
        id=job.id,
        is_archived=job.is_archived,
        message="Job archived.",
    )
