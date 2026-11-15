"""Career-page source onboarding, testing, activation, and history routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.core.exceptions import HydraJobError
from app.db.base import utc_now
from app.db.models import CompanySource, IngestionRun, Job, JobSourceReference
from app.db.repositories import crud, workflows
from app.schemas.common import PaginatedResponse, SourceStatus
from app.schemas.company import CompanySourceResponse
from app.schemas.discovery import (
    IngestionRunResponse,
    SourceContentRequest,
    SourceRegisterRequest,
    SourceTestResponse,
)
from app.schemas.job import JobResponse
from app.services.scraping import (
    SSRFValidationError,
    canonicalize_job_url,
    get_adapter,
    inspect_and_recommend_adapter,
    safe_fetch_url,
    validate_safe_url,
)

router = APIRouter(
    prefix="/sources",
    tags=["sources"],
    dependencies=[Depends(verify_api_key)],
)


@router.post(
    "/register",
    response_model=CompanySourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_source(
    payload: SourceRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Validate URL, detect ATS/adapter, and register a career-page source."""
    offline = payload.sample_content is not None
    try:
        safe_url = validate_safe_url(payload.career_url, resolve_dns=not offline)
    except SSRFValidationError as exc:
        raise HydraJobError(
            str(exc),
            code="ssrf_blocked",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    canon_url = canonicalize_job_url(safe_url)
    existing = db.scalars(
        select(CompanySource).where(CompanySource.canonical_url == canon_url)
    ).first()
    if existing is not None:
        raise HydraJobError(
            "A source with this canonical career URL already exists.",
            code="duplicate_source",
            status_code=status.HTTP_409_CONFLICT,
        )

    company = workflows._resolve_or_create_company(
        db,
        company_id=payload.company_id,
        company_name=payload.company_name,
        website=payload.website,
        industry=payload.industry,
        fallback_url=safe_url,
    )

    inspection = inspect_and_recommend_adapter(
        safe_url,
        sample_content=payload.sample_content,
        resolve_dns=False,
    )

    source = CompanySource(
        company_id=company.id,
        source_name=(payload.source_name or f"{company.name} Careers").strip()[:200],
        career_url=safe_url[:1000],
        canonical_url=canon_url[:1000],
        source_type=payload.source_type,
        extraction_method=inspection.recommended_adapter,
        adapter_name=inspection.recommended_adapter,
        status=inspection.status,
        config_json={
            "detected_ats": inspection.detected_ats,
            "api_endpoint": inspection.api_endpoint,
            "reason": inspection.reason,
        },
        is_active=(inspection.status == SourceStatus.READY.value),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return CompanySourceResponse.model_validate(source)


@router.post("/{source_id}/test", response_model=SourceTestResponse)
async def test_source(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[SourceContentRequest | None, Body()] = None,
) -> SourceTestResponse:
    """Test adapter detection and sample listing extraction for a career source."""
    source = crud.get_source(db, source_id)
    company = crud.get_company(db, source.company_id)
    now = utc_now()
    errors: list[str] = []

    content = payload.sample_content if payload else None
    if content is None:
        try:
            adapter_candidate = get_adapter(source.adapter_name)
            fetch_target = adapter_candidate.build_listing_url(source.career_url)
            fetch_res = await safe_fetch_url(fetch_target, timeout=15.0)
            if fetch_res.status_code >= 400:
                errors.append(f"Target returned HTTP {fetch_res.status_code}")
            else:
                content = fetch_res.text
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    inspection = inspect_and_recommend_adapter(
        source.career_url,
        sample_content=content,
        resolve_dns=False,
    )
    adapter = get_adapter(inspection.recommended_adapter)

    sample_jobs: list[dict] = []
    if content is not None and not errors:
        try:
            listings = adapter.parse_listings(
                content,
                source.career_url,
                company_name=company.name,
            )
            sample_jobs = [item.model_dump() for item in listings[:10]]
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    source.last_checked_at = now
    source.adapter_name = inspection.recommended_adapter
    source.status = (
        SourceStatus.NEEDS_CONFIGURATION.value
        if errors
        else inspection.status
    )
    source.last_error = "; ".join(errors) if errors else None
    db.commit()

    return SourceTestResponse(
        source_id=source.id,
        adapter_name=source.adapter_name,
        detected_ats=inspection.detected_ats,
        status=source.status,
        sample_jobs=sample_jobs,
        errors=errors,
    )


@router.post("/{source_id}/activate", response_model=CompanySourceResponse)
def activate_source(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Enable active monitoring for a career source."""
    source = crud.get_source(db, source_id)
    source.is_active = True
    source.status = SourceStatus.READY.value
    db.commit()
    db.refresh(source)
    return CompanySourceResponse.model_validate(source)


@router.post("/{source_id}/deactivate", response_model=CompanySourceResponse)
def deactivate_source(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> CompanySourceResponse:
    """Disable active monitoring for a career source."""
    source = crud.get_source(db, source_id)
    source.is_active = False
    source.status = SourceStatus.DISABLED.value
    db.commit()
    db.refresh(source)
    return CompanySourceResponse.model_validate(source)


@router.get("/{source_id}/jobs", response_model=PaginatedResponse[JobResponse])
def list_source_jobs(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobResponse]:
    """List jobs discovered from a specific career source."""
    crud.get_source(db, source_id)
    stmt = (
        select(Job)
        .join(JobSourceReference, JobSourceReference.job_id == Job.id)
        .where(JobSourceReference.source_id == source_id, Job.is_archived.is_(False))
        .distinct()
        .order_by(Job.last_seen_at.desc())
    )
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[JobResponse](
        items=[JobResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{source_id}/scans", response_model=PaginatedResponse[IngestionRunResponse])
def list_source_scans(
    source_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[IngestionRunResponse]:
    """List scan runs executed for a specific career source."""
    crud.get_source(db, source_id)
    stmt = (
        select(IngestionRun)
        .where(IngestionRun.source_id == source_id)
        .order_by(IngestionRun.started_at.desc())
    )
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[IngestionRunResponse](
        items=[IngestionRunResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
