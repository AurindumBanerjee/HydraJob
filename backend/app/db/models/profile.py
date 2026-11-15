"""User profile and resume ORM models."""

import uuid

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    """Configurable user profile used for eligibility and job matching."""

    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    degree: Mapped[str | None] = mapped_column(String(120), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    university: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cgpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    projects: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    excluded_locations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    work_authorization: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Resume(Base, TimestampMixin):
    """Resume version metadata and extracted skill profile."""

    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
