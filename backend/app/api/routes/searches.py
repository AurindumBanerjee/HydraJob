"""Saved job search configuration CRUD API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.common import ArchiveResponse, PaginatedResponse
from app.schemas.search import JobSearchCreate, JobSearchResponse, JobSearchUpdate

router = APIRouter(
    prefix="/searches",
    tags=["searches"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=PaginatedResponse[JobSearchResponse])
def list_searches(
    db: Annotated[Session, Depends(get_db)],
    is_active: bool | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobSearchResponse]:
    """List saved job search configurations."""
    items, total = crud.list_searches(
        db,
        is_active=is_active,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[JobSearchResponse](
        items=[JobSearchResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=JobSearchResponse, status_code=status.HTTP_201_CREATED)
def create_search(
    payload: JobSearchCreate,
    db: Annotated[Session, Depends(get_db)],
) -> JobSearchResponse:
    """Create a saved job search configuration."""
    search = crud.create_search(db, payload)
    return JobSearchResponse.model_validate(search)


@router.get("/{search_id}", response_model=JobSearchResponse)
def get_search(
    search_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> JobSearchResponse:
    """Retrieve a saved job search configuration."""
    search = crud.get_search(db, search_id)
    return JobSearchResponse.model_validate(search)


@router.put("/{search_id}", response_model=JobSearchResponse)
def update_search(
    search_id: UUID,
    payload: JobSearchUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> JobSearchResponse:
    """Update a saved job search configuration."""
    search = crud.update_search(db, search_id, payload)
    return JobSearchResponse.model_validate(search)


@router.delete("/{search_id}", response_model=ArchiveResponse)
def archive_search(
    search_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive a saved job search configuration."""
    search = crud.archive_search(db, search_id)
    return ArchiveResponse(
        id=search.id,
        is_archived=search.is_archived,
        message="Job search archived.",
    )
