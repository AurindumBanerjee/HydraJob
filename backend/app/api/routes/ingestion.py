"""Job URL ingestion and reprocessing API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.core.exceptions import HydraJobError
from app.db.models import IngestionRun
from app.db.repositories import workflows
from app.schemas.discovery import IngestionRunResponse, JobIngestRequest

router = APIRouter(
    prefix="/jobs/ingest",
    tags=["ingestion"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("", response_model=IngestionRunResponse, status_code=status.HTTP_200_OK)
async def ingest_job_url(
    payload: JobIngestRequest,
    db: Annotated[Session, Depends(get_db)],
) -> IngestionRunResponse:
    """Validate, fetch, extract, deduplicate, and save a job from a submitted URL."""
    run = await workflows.execute_url_ingestion(
        db,
        url=payload.url,
        company_id=payload.company_id,
        source_id=payload.source_id,
        use_ollama=payload.use_ollama,
        html_content=payload.html_content,
        raw_payload=payload.raw_payload,
    )
    return IngestionRunResponse.model_validate(run)


@router.get("/{run_id}", response_model=IngestionRunResponse)
def get_ingestion_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> IngestionRunResponse:
    """Retrieve status and results of a URL ingestion run."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HydraJobError(
            "Ingestion run not found.",
            code="ingestion_run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return IngestionRunResponse.model_validate(run)


@router.post("/{run_id}/reprocess", response_model=IngestionRunResponse)
async def reprocess_ingestion_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[JobIngestRequest | None, Body()] = None,
) -> IngestionRunResponse:
    """Re-run a URL ingestion within max_retries."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HydraJobError(
            "Ingestion run not found.",
            code="ingestion_run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if run.retry_count >= run.max_retries:
        raise HydraJobError(
            "Maximum retry limit reached for this ingestion run.",
            code="max_retries_exceeded",
            status_code=status.HTTP_409_CONFLICT,
        )
    target_url = (payload.url if payload else None) or run.url
    if not target_url:
        raise HydraJobError(
            "Ingestion run has no URL to reprocess.",
            code="missing_url",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    run.retry_count += 1
    updated_run = await workflows.execute_url_ingestion(
        db,
        url=target_url,
        company_id=payload.company_id if payload else None,
        source_id=payload.source_id if payload else run.source_id,
        use_ollama=payload.use_ollama if payload else True,
        html_content=payload.html_content if payload else None,
        raw_payload=payload.raw_payload if payload else None,
        existing_run=run,
    )
    return IngestionRunResponse.model_validate(updated_run)
