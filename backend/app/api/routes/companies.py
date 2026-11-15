"""Company and career-page source CRUD API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.common import ArchiveResponse, PaginatedResponse, SourceStatus
from app.schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanySourceCreate,
    CompanySourceResponse,
    CompanySourceUpdate,
    CompanyUpdate,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/companies", response_model=PaginatedResponse[CompanyResponse], tags=["companies"])
def list_companies(
    db: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    industry: str | None = None,
    include_archived: bool = False,
    sort_by: str = "name",
    sort_order: str = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[CompanyResponse]:
    """List companies with filtering, sorting, and pagination."""
    items, total = crud.list_companies(
        db,
        include_archived=include_archived,
        search=search,
        industry=industry,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[CompanyResponse](
        items=[CompanyResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["companies"],
)
def create_company(
    payload: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
) -> CompanyResponse:
    """Create a tracked company."""
    company = crud.create_company(db, payload)
    return CompanyResponse.model_validate(company)


@router.get("/companies/{company_id}", response_model=CompanyResponse, tags=["companies"])
def get_company(
    company_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> CompanyResponse:
    """Retrieve a company by ID."""
    company = crud.get_company(db, company_id)
    return CompanyResponse.model_validate(company)


@router.put("/companies/{company_id}", response_model=CompanyResponse, tags=["companies"])
def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> CompanyResponse:
    """Update a company record."""
    company = crud.update_company(db, company_id, payload)
    return CompanyResponse.model_validate(company)


@router.delete("/companies/{company_id}", response_model=ArchiveResponse, tags=["companies"])
def archive_company(
    company_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive a company."""
    company = crud.archive_company(db, company_id)
    return ArchiveResponse(
        id=company.id,
        is_archived=company.is_archived,
        message="Company archived.",
    )


@router.get("/sources", response_model=PaginatedResponse[CompanySourceResponse], tags=["sources"])
def list_sources(
    db: Annotated[Session, Depends(get_db)],
    company_id: UUID | None = None,
    is_active: bool | None = None,
    status_filter: Annotated[SourceStatus | None, Query(alias="status")] = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[CompanySourceResponse]:
    """List career-page sources with filtering and pagination."""
    items, total = crud.list_sources(
        db,
        company_id=company_id,
        is_active=is_active,
        status_filter=status_filter.value if status_filter else None,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[CompanySourceResponse](
        items=[CompanySourceResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/sources",
    response_model=CompanySourceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sources"],
)
def create_source(
    payload: CompanySourceCreate,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Register a company career-page source."""
    source = crud.create_source(db, payload)
    return CompanySourceResponse.model_validate(source)


@router.get("/sources/{source_id}", response_model=CompanySourceResponse, tags=["sources"])
def get_source(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Retrieve a career-page source by ID."""
    source = crud.get_source(db, source_id)
    return CompanySourceResponse.model_validate(source)


@router.put("/sources/{source_id}", response_model=CompanySourceResponse, tags=["sources"])
def update_source(
    source_id: UUID,
    payload: CompanySourceUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Update a career-page source."""
    source = crud.update_source(db, source_id, payload)
    return CompanySourceResponse.model_validate(source)


@router.delete("/sources/{source_id}", response_model=ArchiveResponse, tags=["sources"])
def archive_source(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive a career-page source."""
    source = crud.archive_source(db, source_id)
    return ArchiveResponse(
        id=source.id,
        is_archived=source.is_archived,
        message="Company source archived.",
    )
