"""Discovery scans, search execution, run history, and retry API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.core.exceptions import HydraJobError
from app.db.models import CompanySource, IngestionRun, Job
from app.db.repositories import crud, workflows
from app.schemas.common import PaginatedResponse
from app.schemas.company import CompanySourceResponse
from app.schemas.discovery import (
    DiscoveryTriggerResponse,
    IngestionRunResponse,
    SourceContentRequest,
)
from app.schemas.job import JobResponse

router = APIRouter(tags=["discovery"], dependencies=[Depends(verify_api_key)])


@router.post("/discovery/scan-source/{source_id}", response_model=DiscoveryTriggerResponse)
@router.post("/sources/{source_id}/scan", response_model=DiscoveryTriggerResponse)
async def scan_source_endpoint(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[SourceContentRequest | None, Body()] = None,
) -> DiscoveryTriggerResponse:
    """Trigger a discovery scan for a single career-page source."""
    source = crud.get_source(db, source_id)
    run = await workflows.scan_single_source(
        db,
        source=source,
        sample_content=payload.sample_content if payload else None,
    )
    return DiscoveryTriggerResponse(
        runs=[IngestionRunResponse.model_validate(run)],
        total_discovered=run.jobs_discovered,
        total_new=run.jobs_new,
        total_updated=run.jobs_updated,
    )


@router.post("/discovery/scan-all", response_model=DiscoveryTriggerResponse)
async def scan_all_sources_endpoint(
    db: Annotated[Session, Depends(get_db)],
) -> DiscoveryTriggerResponse:
    """Scan all active non-archived sources with per-source failure isolation."""
    sources = list(
        db.scalars(
            select(CompanySource).where(
                CompanySource.is_active.is_(True),
                CompanySource.is_archived.is_(False),
            )
        ).all()
    )
    runs: list[IngestionRunResponse] = []
    total_discovered = 0
    total_new = 0
    total_updated = 0

    for source in sources:
        run = await workflows.scan_single_source(db, source=source)
        runs.append(IngestionRunResponse.model_validate(run))
        total_discovered += run.jobs_discovered
        total_new += run.jobs_new
        total_updated += run.jobs_updated

    return DiscoveryTriggerResponse(
        runs=runs,
        total_discovered=total_discovered,
        total_new=total_new,
        total_updated=total_updated,
    )


@router.post("/discovery/run-search/{search_id}", response_model=DiscoveryTriggerResponse)
async def run_search_endpoint(
    search_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DiscoveryTriggerResponse:
    """Execute a saved JobSearch filter and evaluate qualifying active jobs."""
    search = crud.get_search(db, search_id)
    run = await workflows.execute_search_run(db, search=search)
    return DiscoveryTriggerResponse(
        runs=[IngestionRunResponse.model_validate(run)],
        total_discovered=run.jobs_discovered,
        total_new=run.jobs_new,
        total_updated=run.jobs_updated,
    )


@router.get("/discovery/runs", response_model=PaginatedResponse[IngestionRunResponse])
def list_discovery_runs(
    db: Annotated[Session, Depends(get_db)],
    run_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[IngestionRunResponse]:
    """List URL ingestion, source scan, and search runs."""
    stmt = select(IngestionRun)
    if run_type:
        stmt = stmt.where(IngestionRun.run_type == run_type)
    if status_filter:
        stmt = stmt.where(IngestionRun.status == status_filter)
    stmt = stmt.order_by(IngestionRun.started_at.desc())

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[IngestionRunResponse](
        items=[IngestionRunResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/discovery/runs/{run_id}", response_model=IngestionRunResponse)
def get_discovery_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> IngestionRunResponse:
    """Retrieve a single ingestion or discovery run."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HydraJobError(
            "Discovery run not found.",
            code="run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return IngestionRunResponse.model_validate(run)


@router.post("/discovery/runs/{run_id}/retry", response_model=IngestionRunResponse)
async def retry_discovery_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[SourceContentRequest | None, Body()] = None,
) -> IngestionRunResponse:
    """Retry a failed or incomplete ingestion/source scan within max_retries."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HydraJobError(
            "Discovery run not found.",
            code="run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if run.retry_count >= run.max_retries:
        raise HydraJobError(
            "Maximum retry limit reached for this run.",
            code="max_retries_exceeded",
            status_code=status.HTTP_409_CONFLICT,
        )

    run.retry_count += 1
    if run.run_type == "SOURCE_SCAN" and run.source_id is not None:
        source = crud.get_source(db, run.source_id)
        db.commit()
        new_run = await workflows.scan_single_source(
            db,
            source=source,
            sample_content=payload.sample_content if payload else None,
        )
        return IngestionRunResponse.model_validate(new_run)

    if not run.url:
        raise HydraJobError(
            "Run has no URL to retry.",
            code="missing_url",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    updated = await workflows.execute_url_ingestion(
        db,
        url=run.url,
        source_id=run.source_id,
        html_content=payload.sample_content if payload else None,
        existing_run=run,
    )
    return IngestionRunResponse.model_validate(updated)


@router.get("/discovery/new-jobs", response_model=PaginatedResponse[JobResponse])
def list_newly_discovered_jobs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobResponse]:
    """List recently discovered active jobs ordered by first_seen_at descending."""
    stmt = (
        select(Job)
        .where(Job.is_archived.is_(False), Job.is_active.is_(True))
        .order_by(Job.first_seen_at.desc())
    )
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[JobResponse](
        items=[JobResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/discovery/failed-sources", response_model=PaginatedResponse[CompanySourceResponse])
def list_failed_sources(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[CompanySourceResponse]:
    """List non-archived career sources with recent scan errors."""
    stmt = (
        select(CompanySource)
        .where(
            CompanySource.is_archived.is_(False),
            or_(
                CompanySource.consecutive_failures > 0,
                CompanySource.last_error.is_not(None),
            ),
        )
        .order_by(CompanySource.consecutive_failures.desc(), CompanySource.updated_at.desc())
    )
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[CompanySourceResponse](
        items=[CompanySourceResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
