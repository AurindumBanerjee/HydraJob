"""User profile and resume management API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.common import ArchiveResponse, PaginatedResponse
from app.schemas.profile import (
    ResumeCreate,
    ResumeResponse,
    ResumeUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/profile", response_model=UserProfileResponse, tags=["profile"])
def get_profile(db: Annotated[Session, Depends(get_db)]) -> UserProfileResponse:
    """Return the active user profile, seeding the initial record on first access."""
    profile = crud.get_or_seed_profile(db)
    return UserProfileResponse.model_validate(profile)


@router.put("/profile", response_model=UserProfileResponse, tags=["profile"])
def update_profile(
    payload: UserProfileUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> UserProfileResponse:
    """Update the user profile."""
    profile = crud.update_profile(db, payload)
    return UserProfileResponse.model_validate(profile)


@router.get("/resumes", response_model=PaginatedResponse[ResumeResponse], tags=["resumes"])
def list_resumes(
    db: Annotated[Session, Depends(get_db)],
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[ResumeResponse]:
    """List resume versions with pagination."""
    items, total = crud.list_resumes(
        db,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[ResumeResponse](
        items=[ResumeResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/resumes",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["resumes"],
)
def create_resume(
    payload: ResumeCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ResumeResponse:
    """Create a resume version."""
    resume = crud.create_resume(db, payload)
    return ResumeResponse.model_validate(resume)


@router.get("/resumes/{resume_id}", response_model=ResumeResponse, tags=["resumes"])
def get_resume(
    resume_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ResumeResponse:
    """Retrieve a single resume version."""
    resume = crud.get_resume(db, resume_id)
    return ResumeResponse.model_validate(resume)


@router.put("/resumes/{resume_id}", response_model=ResumeResponse, tags=["resumes"])
def update_resume(
    resume_id: UUID,
    payload: ResumeUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ResumeResponse:
    """Update resume metadata or preferred status."""
    resume = crud.update_resume(db, resume_id, payload)
    return ResumeResponse.model_validate(resume)


@router.delete("/resumes/{resume_id}", response_model=ArchiveResponse, tags=["resumes"])
def archive_resume(
    resume_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive a resume version."""
    resume = crud.archive_resume(db, resume_id)
    return ArchiveResponse(
        id=resume.id,
        is_archived=resume.is_archived,
        message="Resume archived.",
    )
