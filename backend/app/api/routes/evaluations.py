"""Job eligibility and relevance evaluation API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.models import JobEvaluation
from app.db.repositories import crud, workflows
from app.schemas.common import PaginatedResponse
from app.schemas.job import JobEvaluateRequest, JobEvaluationResponse

router = APIRouter(
    prefix="/jobs",
    tags=["evaluations"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/{job_id}/evaluate", response_model=JobEvaluationResponse)
async def evaluate_job_endpoint(
    job_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[JobEvaluateRequest | None, Body()] = None,
) -> JobEvaluationResponse:
    """Evaluate a job against the user profile and generate idempotent tasks."""
    job = crud.get_job(db, job_id)
    evaluation = await workflows.evaluate_job_and_create_tasks(
        db,
        job=job,
        resume_id=payload.resume_id if payload else None,
        use_ollama=payload.use_ollama if payload else False,
    )
    return JobEvaluationResponse.model_validate(evaluation)


@router.get("/{job_id}/evaluations", response_model=PaginatedResponse[JobEvaluationResponse])
def list_job_evaluations(
    job_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[JobEvaluationResponse]:
    """List historical evaluations for a job."""
    crud.get_job(db, job_id)
    stmt = (
        select(JobEvaluation)
        .where(JobEvaluation.job_id == job_id)
        .order_by(JobEvaluation.evaluated_at.desc())
    )
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[JobEvaluationResponse](
        items=[JobEvaluationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
