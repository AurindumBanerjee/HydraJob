"""Recruitment email intelligence and manual review API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.models import EmailMessage
from app.db.repositories import workflows
from app.schemas.common import PaginatedResponse
from app.schemas.email import (
    EmailMessageResponse,
    EmailReviewRequest,
    EmailSyncRequest,
    SyntheticEmailIngestRequest,
)
from app.services.email import SyntheticGmailAdapter

router = APIRouter(prefix="/emails", tags=["emails"], dependencies=[Depends(verify_api_key)])


@router.post("/ingest-synthetic", response_model=EmailMessageResponse)
@router.post("/ingest", response_model=EmailMessageResponse)
async def ingest_synthetic_email(
    payload: SyntheticEmailIngestRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmailMessageResponse:
    """Idempotently classify, match, and process a synthetic recruitment email."""
    record = await workflows.process_email_message(db, payload=payload, use_ollama=False)
    return EmailMessageResponse.model_validate(record)


@router.post("/sync", response_model=PaginatedResponse[EmailMessageResponse])
async def sync_emails(
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[EmailSyncRequest | None, Body()] = None,
) -> PaginatedResponse[EmailMessageResponse]:
    """Sync a batch of synthetic recruitment messages via SyntheticGmailAdapter."""
    raw_messages = [m.model_dump() for m in payload.messages] if payload else []
    adapter = SyntheticGmailAdapter(raw_messages)
    batch = await adapter.fetch_messages()
    use_ollama = bool(payload and payload.use_ollama)

    processed: list[EmailMessageResponse] = []
    for item in batch.messages:
        req = SyntheticEmailIngestRequest(
            gmail_message_id=item.gmail_message_id,
            thread_id=item.thread_id,
            sender=item.sender,
            subject=item.subject,
            snippet=item.snippet,
            received_at=item.received_at,
        )
        record = await workflows.process_email_message(db, payload=req, use_ollama=use_ollama)
        processed.append(EmailMessageResponse.model_validate(record))

    return PaginatedResponse[EmailMessageResponse](
        items=processed,
        total=len(processed),
        limit=max(len(processed), 1),
        offset=0,
    )


@router.get("", response_model=PaginatedResponse[EmailMessageResponse])
@router.get("/messages", response_model=PaginatedResponse[EmailMessageResponse])
def list_email_messages(
    db: Annotated[Session, Depends(get_db)],
    needs_review: bool | None = None,
    classification: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[EmailMessageResponse]:
    """List recruitment email records with review queue and classification filters."""
    stmt = select(EmailMessage)
    if needs_review is not None:
        stmt = stmt.where(EmailMessage.needs_review.is_(needs_review))
    if classification:
        stmt = stmt.where(EmailMessage.classification == classification)
    stmt = stmt.order_by(EmailMessage.received_at.desc())

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return PaginatedResponse[EmailMessageResponse](
        items=[EmailMessageResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{email_id}/review", response_model=EmailMessageResponse)
@router.post("/messages/{email_id}/review", response_model=EmailMessageResponse)
def review_email_message(
    email_id: UUID,
    payload: EmailReviewRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmailMessageResponse:
    """Confirm or correct an email classification/match and optionally apply status update."""
    updated = workflows.review_email_and_optionally_apply(
        db,
        email_id=email_id,
        classification=payload.classification,
        matched_application_id=payload.matched_application_id,
        apply_status_update=payload.apply_status_update,
        needs_review=payload.needs_review,
        review_notes=payload.review_notes,
    )
    return EmailMessageResponse.model_validate(updated)
