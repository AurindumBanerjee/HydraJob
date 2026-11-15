"""Internal task CRUD API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, verify_api_key
from app.db.repositories import crud
from app.schemas.common import ArchiveResponse, PaginatedResponse, PriorityLevel, TaskStatus
from app.schemas.task import TaskCreate, TaskResponse, TaskStatusUpdate, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=PaginatedResponse[TaskResponse])
def list_tasks(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: PriorityLevel | None = None,
    job_id: UUID | None = None,
    application_id: UUID | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[TaskResponse]:
    """List internal tasks with filtering and pagination."""
    items, total = crud.list_tasks(
        db,
        status_filter=status_filter.value if status_filter else None,
        priority=priority.value if priority else None,
        job_id=job_id,
        application_id=application_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[TaskResponse](
        items=[TaskResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Annotated[Session, Depends(get_db)],
) -> TaskResponse:
    """Create an internal task."""
    task = crud.create_task(db, payload)
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> TaskResponse:
    """Retrieve a task by ID."""
    task = crud.get_task(db, task_id)
    return TaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TaskResponse:
    """Update task attributes."""
    task = crud.update_task(db, task_id, payload)
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: UUID,
    payload: TaskStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TaskResponse:
    """Transition an internal task status."""
    task = crud.update_task_status(db, task_id, payload)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", response_model=ArchiveResponse)
def archive_task(
    task_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ArchiveResponse:
    """Soft-archive an internal task."""
    task = crud.archive_task(db, task_id)
    return ArchiveResponse(
        id=task.id,
        is_archived=task.is_archived,
        message="Task archived.",
    )
