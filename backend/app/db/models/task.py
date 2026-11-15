"""Internal task ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Task(Base, TimestampMixin):
    """Internal actionable task associated optionally with a job or application."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), default="GENERAL", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="MEDIUM", nullable=False)
    external_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
