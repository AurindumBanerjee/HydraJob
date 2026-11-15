"""Pydantic schemas for internal tasks."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PriorityLevel, TaskStatus


class TaskCreate(BaseModel):
    """Payload for creating an internal task."""

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    task_type: str = Field(default="GENERAL", max_length=64)
    due_date: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: PriorityLevel = PriorityLevel.MEDIUM
    external_task_id: str | None = Field(default=None, max_length=200)


class TaskUpdate(BaseModel):
    """Payload for updating task fields."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    task_type: str | None = Field(default=None, max_length=64)
    due_date: datetime | None = None
    status: TaskStatus | None = None
    priority: PriorityLevel | None = None
    external_task_id: str | None = Field(default=None, max_length=200)
    is_archived: bool | None = None


class TaskStatusUpdate(BaseModel):
    """Payload for transitioning task status."""

    status: TaskStatus


class TaskResponse(BaseModel):
    """Serialized internal task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    task_type: str
    due_date: datetime | None = None
    status: str
    priority: str
    external_task_id: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
