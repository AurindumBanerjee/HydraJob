"""CRUD repository helpers for Phase 1 domain entities."""

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import HydraJobError
from app.db.base import utc_now
from app.db.models import (
    ApplicationEvent,
    Company,
    CompanySource,
    Job,
    JobApplication,
    JobSearch,
    JobSourceReference,
    Resume,
    Task,
    UserProfile,
)
from app.schemas.application import (
    JobApplicationCreate,
    JobApplicationStatusUpdate,
    JobApplicationUpdate,
)
from app.schemas.common import ApplicationStatus, JobStatus, SourceStatus
from app.schemas.company import (
    CompanyCreate,
    CompanySourceCreate,
    CompanySourceUpdate,
    CompanyUpdate,
)
from app.schemas.job import JobCreate, JobUpdate
from app.schemas.profile import ResumeCreate, ResumeUpdate, UserProfileUpdate
from app.schemas.search import JobSearchCreate, JobSearchUpdate
from app.schemas.task import TaskCreate, TaskStatusUpdate, TaskUpdate

_TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
)


def normalize_text(value: str) -> str:
    """Normalize names, titles, and locations for case-insensitive matching."""
    return re.sub(r"\s+", " ", value.strip().lower())


def canonicalize_url(raw_url: str) -> str:
    """Normalize URL scheme, host, tracking query parameters, and trailing slash."""
    cleaned = raw_url.strip()
    parts = urlsplit(cleaned)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    query = urlencode(sorted(filtered_query))
    return urlunsplit((scheme, netloc, path, query, ""))


def _paginate(
    db: Session,
    stmt: Select[tuple[Any]],
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())
    items = list(db.scalars(stmt.limit(limit).offset(offset)).all())
    return items, total


# ---------------------------------------------------------------------------
# Profile & Resumes
# ---------------------------------------------------------------------------


def get_or_seed_profile(db: Session) -> UserProfile:
    """Return the active user profile, seeding the initial default record once."""
    profile = db.scalars(select(UserProfile).order_by(UserProfile.created_at.asc())).first()
    if profile is not None:
        return profile

    profile = UserProfile(
        name="HydraJob Candidate",
        education="B.Tech in Computer Science and Engineering, IIT Jodhpur",
        degree="B.Tech",
        branch="Computer Science and Engineering",
        university="IIT Jodhpur",
        graduation_year=2027,
        experience_summary="Data Science Intern at InfoEdge",
        projects=[
            "Script-Identifier",
            "TinyML",
            "ANN in C",
            "Smart Surveillance",
            "Company-Knowledge Model Research",
        ],
        skills=[
            "Python",
            "C++",
            "SQL",
            "PyTorch",
            "Machine Learning",
            "NLP",
            "LLMs",
            "RAG",
            "Computer Vision",
            "Model Fine-tuning",
        ],
        preferred_roles=[
            "Machine Learning Engineer",
            "Data Scientist",
            "AI Engineer",
            "Software Engineer",
        ],
        preferred_locations=[],
        excluded_locations=[],
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(db: Session, payload: UserProfileUpdate) -> UserProfile:
    """Update configurable user profile attributes."""
    profile = get_or_seed_profile(db)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(profile, field_name, value)
    db.commit()
    db.refresh(profile)
    return profile


def list_resumes(
    db: Session,
    *,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Resume], int]:
    """List resume versions with pagination."""
    stmt = select(Resume)
    if not include_archived:
        stmt = stmt.where(Resume.is_archived.is_(False))
    stmt = stmt.order_by(Resume.is_preferred.desc(), Resume.updated_at.desc())
    return _paginate(db, stmt, limit, offset)


def get_resume(db: Session, resume_id: UUID) -> Resume:
    """Retrieve a single resume or raise 404."""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HydraJobError(
            "Resume not found.",
            code="resume_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return resume


def create_resume(db: Session, payload: ResumeCreate) -> Resume:
    """Create a resume version, maintaining a single preferred resume if requested."""
    if payload.is_preferred:
        for existing in db.scalars(select(Resume).where(Resume.is_preferred.is_(True))).all():
            existing.is_preferred = False

    resume = Resume(**payload.model_dump())
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def update_resume(db: Session, resume_id: UUID, payload: ResumeUpdate) -> Resume:
    """Update resume metadata or preferred status."""
    resume = get_resume(db, resume_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_preferred") is True:
        for existing in db.scalars(
            select(Resume).where(Resume.is_preferred.is_(True), Resume.id != resume_id)
        ).all():
            existing.is_preferred = False

    for field_name, value in updates.items():
        setattr(resume, field_name, value)
    db.commit()
    db.refresh(resume)
    return resume


def archive_resume(db: Session, resume_id: UUID) -> Resume:
    """Soft-archive a resume version."""
    resume = get_resume(db, resume_id)
    resume.is_archived = True
    resume.is_active = False
    resume.is_preferred = False
    db.commit()
    db.refresh(resume)
    return resume


# ---------------------------------------------------------------------------
# Companies & Career Sources
# ---------------------------------------------------------------------------


def list_companies(
    db: Session,
    *,
    include_archived: bool = False,
    search: str | None = None,
    industry: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> tuple[list[Company], int]:
    """List companies with filtering, sorting, and pagination."""
    stmt = select(Company)
    if not include_archived:
        stmt = stmt.where(Company.is_archived.is_(False))
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(Company.normalized_name.like(term))
    if industry:
        stmt = stmt.where(func.lower(Company.industry) == industry.strip().lower())

    sort_col = {
        "name": Company.name,
        "created_at": Company.created_at,
        "updated_at": Company.updated_at,
    }.get(sort_by, Company.name)
    stmt = stmt.order_by(sort_col.desc() if sort_order.lower() == "desc" else sort_col.asc())
    return _paginate(db, stmt, limit, offset)


def get_company(db: Session, company_id: UUID) -> Company:
    """Retrieve a company by ID or raise 404."""
    company = db.get(Company, company_id)
    if company is None:
        raise HydraJobError(
            "Company not found.",
            code="company_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return company


def create_company(db: Session, payload: CompanyCreate) -> Company:
    """Create a new company, preventing duplicate normalized names."""
    normalized = normalize_text(payload.name)
    existing = db.scalars(select(Company).where(Company.normalized_name == normalized)).first()
    if existing is not None:
        raise HydraJobError(
            f"Company '{payload.name}' already exists.",
            code="duplicate_company",
            status_code=status.HTTP_409_CONFLICT,
        )

    company = Company(
        name=payload.name.strip(),
        normalized_name=normalized,
        website=payload.website,
        industry=payload.industry,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def update_company(db: Session, company_id: UUID, payload: CompanyUpdate) -> Company:
    """Update a company record while enforcing unique normalized name."""
    company = get_company(db, company_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        new_name = updates["name"].strip()
        new_norm = normalize_text(new_name)
        conflict = db.scalars(
            select(Company).where(Company.normalized_name == new_norm, Company.id != company_id)
        ).first()
        if conflict is not None:
            raise HydraJobError(
                f"Company '{new_name}' already exists.",
                code="duplicate_company",
                status_code=status.HTTP_409_CONFLICT,
            )
        company.name = new_name
        company.normalized_name = new_norm
        updates.pop("name")

    for field_name, value in updates.items():
        setattr(company, field_name, value)
    db.commit()
    db.refresh(company)
    return company


def archive_company(db: Session, company_id: UUID) -> Company:
    """Soft-archive a company."""
    company = get_company(db, company_id)
    company.is_archived = True
    db.commit()
    db.refresh(company)
    return company


def list_sources(
    db: Session,
    *,
    company_id: UUID | None = None,
    is_active: bool | None = None,
    status_filter: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CompanySource], int]:
    """List career-page sources with filtering and pagination."""
    stmt = select(CompanySource)
    if not include_archived:
        stmt = stmt.where(CompanySource.is_archived.is_(False))
    if company_id is not None:
        stmt = stmt.where(CompanySource.company_id == company_id)
    if is_active is not None:
        stmt = stmt.where(CompanySource.is_active.is_(is_active))
    if status_filter is not None:
        stmt = stmt.where(CompanySource.status == status_filter)
    stmt = stmt.order_by(CompanySource.created_at.desc())
    return _paginate(db, stmt, limit, offset)


def get_source(db: Session, source_id: UUID) -> CompanySource:
    """Retrieve a career-page source or raise 404."""
    source = db.get(CompanySource, source_id)
    if source is None:
        raise HydraJobError(
            "Company source not found.",
            code="source_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return source


def create_source(db: Session, payload: CompanySourceCreate) -> CompanySource:
    """Create a career-page source after verifying company and URL uniqueness."""
    get_company(db, payload.company_id)
    canon = canonicalize_url(payload.career_url)
    existing = db.scalars(
        select(CompanySource).where(CompanySource.canonical_url == canon)
    ).first()
    if existing is not None:
        raise HydraJobError(
            "A source with this canonical career URL already exists.",
            code="duplicate_source",
            status_code=status.HTTP_409_CONFLICT,
        )

    source = CompanySource(
        company_id=payload.company_id,
        source_name=payload.source_name.strip(),
        career_url=payload.career_url.strip(),
        canonical_url=canon,
        source_type=payload.source_type,
        extraction_method=payload.extraction_method,
        adapter_name=payload.adapter_name,
        status=payload.status.value,
        config_json=payload.config_json,
        is_active=payload.is_active,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source_id: UUID, payload: CompanySourceUpdate) -> CompanySource:
    """Update a career-page source."""
    source = get_source(db, source_id)
    updates = payload.model_dump(exclude_unset=True)
    if "career_url" in updates and updates["career_url"] is not None:
        new_url = updates["career_url"].strip()
        new_canon = canonicalize_url(new_url)
        conflict = db.scalars(
            select(CompanySource).where(
                CompanySource.canonical_url == new_canon,
                CompanySource.id != source_id,
            )
        ).first()
        if conflict is not None:
            raise HydraJobError(
                "Another source already uses this canonical career URL.",
                code="duplicate_source",
                status_code=status.HTTP_409_CONFLICT,
            )
        source.career_url = new_url
        source.canonical_url = new_canon
        updates.pop("career_url")

    if "status" in updates and updates["status"] is not None:
        updates["status"] = updates["status"].value

    for field_name, value in updates.items():
        setattr(source, field_name, value)
    db.commit()
    db.refresh(source)
    return source


def archive_source(db: Session, source_id: UUID) -> CompanySource:
    """Soft-archive and deactivate a career-page source."""
    source = get_source(db, source_id)
    source.is_archived = True
    source.is_active = False
    source.status = SourceStatus.DISABLED.value
    db.commit()
    db.refresh(source)
    return source


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def list_jobs(
    db: Session,
    *,
    company_id: UUID | None = None,
    status_filter: str | None = None,
    is_active: bool | None = None,
    include_archived: bool = False,
    search: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Job], int]:
    """List jobs with filtering, sorting, and pagination."""
    stmt = select(Job)
    if not include_archived:
        stmt = stmt.where(Job.is_archived.is_(False))
    if company_id is not None:
        stmt = stmt.where(Job.company_id == company_id)
    if status_filter is not None:
        stmt = stmt.where(Job.status == status_filter)
    if is_active is not None:
        stmt = stmt.where(Job.is_active.is_(is_active))
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Job.normalized_title.like(term),
                func.lower(func.coalesce(Job.description, "")).like(term),
            )
        )
    if location:
        loc_term = f"%{location.strip().lower()}%"
        stmt = stmt.where(func.coalesce(Job.normalized_location, "").like(loc_term))
    if employment_type:
        stmt = stmt.where(
            func.lower(func.coalesce(Job.employment_type, "")) == employment_type.strip().lower()
        )

    sort_col = {
        "title": Job.title,
        "first_seen_at": Job.first_seen_at,
        "last_seen_at": Job.last_seen_at,
        "application_deadline": Job.application_deadline,
        "created_at": Job.created_at,
        "updated_at": Job.updated_at,
    }.get(sort_by, Job.created_at)
    stmt = stmt.order_by(sort_col.desc() if sort_order.lower() == "desc" else sort_col.asc())
    return _paginate(db, stmt, limit, offset)


def get_job(db: Session, job_id: UUID) -> Job:
    """Retrieve a single job by ID or raise 404."""
    job = db.get(Job, job_id)
    if job is None:
        raise HydraJobError(
            "Job not found.",
            code="job_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return job


def create_job(db: Session, payload: JobCreate) -> Job:
    """Create a job record, preventing duplicates by canonical URL, external ID, or tuple."""
    get_company(db, payload.company_id)

    norm_title = normalize_text(payload.title)
    norm_location = normalize_text(payload.location) if payload.location else None

    raw_canon = payload.canonical_url or payload.application_url
    canon_url = canonicalize_url(raw_canon) if raw_canon else None

    if canon_url:
        existing_url = db.scalars(select(Job).where(Job.canonical_url == canon_url)).first()
        if existing_url is not None:
            raise HydraJobError(
                "A job with this canonical URL already exists.",
                code="duplicate_job",
                status_code=status.HTTP_409_CONFLICT,
            )

    if payload.external_job_id:
        existing_ext = db.scalars(
            select(Job).where(
                Job.company_id == payload.company_id,
                Job.external_job_id == payload.external_job_id,
                Job.is_archived.is_(False),
            )
        ).first()
        if existing_ext is not None:
            raise HydraJobError(
                "A job with this company and external_job_id already exists.",
                code="duplicate_job",
                status_code=status.HTTP_409_CONFLICT,
            )

    loc_clause = (
        Job.normalized_location == norm_location
        if norm_location is not None
        else Job.normalized_location.is_(None)
    )
    existing_composite = db.scalars(
        select(Job).where(
            Job.company_id == payload.company_id,
            Job.normalized_title == norm_title,
            loc_clause,
            Job.is_archived.is_(False),
        )
    ).first()
    if existing_composite is not None:
        raise HydraJobError(
            "A job with the same company, title, and location already exists.",
            code="duplicate_job",
            status_code=status.HTTP_409_CONFLICT,
        )

    now = utc_now()
    data = payload.model_dump()
    data["title"] = payload.title.strip()
    data["normalized_title"] = norm_title
    data["normalized_location"] = norm_location
    data["canonical_url"] = canon_url
    data["status"] = payload.status.value
    data["first_seen_at"] = now
    data["last_seen_at"] = now

    job = Job(**data)
    db.add(job)
    db.flush()

    if canon_url:
        ref = JobSourceReference(
            job_id=job.id,
            source_id=None,
            source_external_id=payload.external_job_id,
            original_url=payload.application_url or canon_url,
            canonical_url=canon_url,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(ref)

    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: UUID, payload: JobUpdate) -> Job:
    """Update a job record while enforcing uniqueness constraints."""
    job = get_job(db, job_id)
    updates = payload.model_dump(exclude_unset=True)

    if "company_id" in updates and updates["company_id"] is not None:
        get_company(db, updates["company_id"])

    if "title" in updates and updates["title"] is not None:
        updates["title"] = updates["title"].strip()
        updates["normalized_title"] = normalize_text(updates["title"])

    if "location" in updates:
        loc = updates["location"]
        updates["normalized_location"] = normalize_text(loc) if loc else None

    if "canonical_url" in updates and updates["canonical_url"] is not None:
        new_canon = canonicalize_url(updates["canonical_url"])
        conflict = db.scalars(
            select(Job).where(Job.canonical_url == new_canon, Job.id != job_id)
        ).first()
        if conflict is not None:
            raise HydraJobError(
                "Another job already uses this canonical URL.",
                code="duplicate_job",
                status_code=status.HTTP_409_CONFLICT,
            )
        updates["canonical_url"] = new_canon

    if "status" in updates and updates["status"] is not None:
        updates["status"] = updates["status"].value

    for field_name, value in updates.items():
        setattr(job, field_name, value)
    job.last_changed_at = utc_now()
    db.commit()
    db.refresh(job)
    return job


def archive_job(db: Session, job_id: UUID) -> Job:
    """Soft-archive a job record."""
    job = get_job(db, job_id)
    job.is_archived = True
    job.is_active = False
    job.status = JobStatus.ARCHIVED.value
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Applications & Immutable Audit Events
# ---------------------------------------------------------------------------


def list_applications(
    db: Session,
    *,
    job_id: UUID | None = None,
    status_filter: str | None = None,
    priority: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[JobApplication], int]:
    """List job applications with filtering and pagination."""
    stmt = select(JobApplication)
    if not include_archived:
        stmt = stmt.where(JobApplication.is_archived.is_(False))
    if job_id is not None:
        stmt = stmt.where(JobApplication.job_id == job_id)
    if status_filter is not None:
        stmt = stmt.where(JobApplication.status == status_filter)
    if priority is not None:
        stmt = stmt.where(JobApplication.priority == priority)
    stmt = stmt.order_by(JobApplication.updated_at.desc())
    return _paginate(db, stmt, limit, offset)


def get_application(db: Session, application_id: UUID) -> JobApplication:
    """Retrieve a single job application or raise 404."""
    application = db.get(JobApplication, application_id)
    if application is None:
        raise HydraJobError(
            "Application not found.",
            code="application_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return application


def create_application(db: Session, payload: JobApplicationCreate) -> JobApplication:
    """Create a job application and record its initial immutable ApplicationEvent."""
    get_job(db, payload.job_id)
    if payload.selected_resume_id is not None:
        get_resume(db, payload.selected_resume_id)

    existing = db.scalars(
        select(JobApplication).where(
            JobApplication.job_id == payload.job_id,
            JobApplication.is_archived.is_(False),
        )
    ).first()
    if existing is not None:
        raise HydraJobError(
            "An active application already exists for this job.",
            code="duplicate_application",
            status_code=status.HTTP_409_CONFLICT,
        )

    now = utc_now()
    application_date = payload.application_date
    if payload.status == ApplicationStatus.APPLIED and application_date is None:
        application_date = now

    application = JobApplication(
        job_id=payload.job_id,
        selected_resume_id=payload.selected_resume_id,
        status=payload.status.value,
        priority=payload.priority.value,
        match_score=payload.match_score,
        eligibility_status=(
            payload.eligibility_status.value if payload.eligibility_status else None
        ),
        application_date=application_date,
        notes=payload.notes,
        thread_id=payload.thread_id,
    )
    db.add(application)
    db.flush()

    event = ApplicationEvent(
        application_id=application.id,
        event_type="CREATED",
        previous_status=None,
        new_status=application.status,
        source="manual",
        description=payload.notes or "Application created",
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(application)
    return application


def update_application(
    db: Session, application_id: UUID, payload: JobApplicationUpdate
) -> JobApplication:
    """Update non-status metadata on a job application."""
    application = get_application(db, application_id)
    updates = payload.model_dump(exclude_unset=True)
    if "selected_resume_id" in updates and updates["selected_resume_id"] is not None:
        get_resume(db, updates["selected_resume_id"])
    if "priority" in updates and updates["priority"] is not None:
        updates["priority"] = updates["priority"].value
    if "eligibility_status" in updates and updates["eligibility_status"] is not None:
        updates["eligibility_status"] = updates["eligibility_status"].value

    for field_name, value in updates.items():
        setattr(application, field_name, value)
    db.commit()
    db.refresh(application)
    return application


def update_application_status(
    db: Session,
    application_id: UUID,
    payload: JobApplicationStatusUpdate,
) -> JobApplication:
    """Transition application status and append an immutable ApplicationEvent."""
    application = get_application(db, application_id)
    previous_status = application.status
    new_status = payload.status.value
    now = utc_now()

    application.status = new_status
    if payload.notes is not None:
        application.notes = payload.notes
    if payload.application_date is not None:
        application.application_date = payload.application_date
    elif payload.status == ApplicationStatus.APPLIED and application.application_date is None:
        application.application_date = now

    event = ApplicationEvent(
        application_id=application.id,
        event_type="STATUS_CHANGED",
        previous_status=previous_status,
        new_status=new_status,
        source=payload.source,
        description=payload.description or payload.notes or f"Status changed to {new_status}",
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(application)
    return application


def list_application_events(
    db: Session,
    application_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ApplicationEvent], int]:
    """Return immutable chronological events for an application."""
    get_application(db, application_id)
    stmt = (
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.occurred_at.asc())
    )
    return _paginate(db, stmt, limit, offset)


def archive_application(db: Session, application_id: UUID) -> JobApplication:
    """Soft-archive an application while preserving its historical events."""
    application = get_application(db, application_id)
    application.is_archived = True
    event = ApplicationEvent(
        application_id=application.id,
        event_type="ARCHIVED",
        previous_status=application.status,
        new_status=application.status,
        source="manual",
        description="Application archived",
        occurred_at=utc_now(),
    )
    db.add(event)
    db.commit()
    db.refresh(application)
    return application


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def list_tasks(
    db: Session,
    *,
    status_filter: str | None = None,
    priority: str | None = None,
    job_id: UUID | None = None,
    application_id: UUID | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Task], int]:
    """List internal tasks with filtering and pagination."""
    stmt = select(Task)
    if not include_archived:
        stmt = stmt.where(Task.is_archived.is_(False))
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if job_id is not None:
        stmt = stmt.where(Task.job_id == job_id)
    if application_id is not None:
        stmt = stmt.where(Task.application_id == application_id)
    stmt = stmt.order_by(Task.created_at.desc())
    return _paginate(db, stmt, limit, offset)


def get_task(db: Session, task_id: UUID) -> Task:
    """Retrieve a task by ID or raise 404."""
    task = db.get(Task, task_id)
    if task is None:
        raise HydraJobError(
            "Task not found.",
            code="task_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return task


def create_task(db: Session, payload: TaskCreate) -> Task:
    """Create an internal task after validating optional linked records."""
    if payload.job_id is not None:
        get_job(db, payload.job_id)
    if payload.application_id is not None:
        get_application(db, payload.application_id)

    task = Task(
        title=payload.title.strip(),
        description=payload.description,
        job_id=payload.job_id,
        application_id=payload.application_id,
        task_type=payload.task_type,
        due_date=payload.due_date,
        status=payload.status.value,
        priority=payload.priority.value,
        external_task_id=payload.external_task_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task_id: UUID, payload: TaskUpdate) -> Task:
    """Update task attributes."""
    task = get_task(db, task_id)
    updates = payload.model_dump(exclude_unset=True)
    if "job_id" in updates and updates["job_id"] is not None:
        get_job(db, updates["job_id"])
    if "application_id" in updates and updates["application_id"] is not None:
        get_application(db, updates["application_id"])
    if "title" in updates and updates["title"] is not None:
        updates["title"] = updates["title"].strip()
    if "status" in updates and updates["status"] is not None:
        updates["status"] = updates["status"].value
    if "priority" in updates and updates["priority"] is not None:
        updates["priority"] = updates["priority"].value

    for field_name, value in updates.items():
        setattr(task, field_name, value)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(db: Session, task_id: UUID, payload: TaskStatusUpdate) -> Task:
    """Transition an internal task status."""
    task = get_task(db, task_id)
    task.status = payload.status.value
    db.commit()
    db.refresh(task)
    return task


def archive_task(db: Session, task_id: UUID) -> Task:
    """Soft-archive a task."""
    task = get_task(db, task_id)
    task.is_archived = True
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Search Configurations
# ---------------------------------------------------------------------------


def list_searches(
    db: Session,
    *,
    is_active: bool | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[JobSearch], int]:
    """List saved job search configurations."""
    stmt = select(JobSearch)
    if not include_archived:
        stmt = stmt.where(JobSearch.is_archived.is_(False))
    if is_active is not None:
        stmt = stmt.where(JobSearch.is_active.is_(is_active))
    stmt = stmt.order_by(JobSearch.created_at.desc())
    return _paginate(db, stmt, limit, offset)


def get_search(db: Session, search_id: UUID) -> JobSearch:
    """Retrieve a search configuration or raise 404."""
    search = db.get(JobSearch, search_id)
    if search is None:
        raise HydraJobError(
            "Job search configuration not found.",
            code="search_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return search


def create_search(db: Session, payload: JobSearchCreate) -> JobSearch:
    """Create a saved job search configuration."""
    search = JobSearch(**payload.model_dump())
    search.name = payload.name.strip()
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


def update_search(db: Session, search_id: UUID, payload: JobSearchUpdate) -> JobSearch:
    """Update a saved job search configuration."""
    search = get_search(db, search_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    for field_name, value in updates.items():
        setattr(search, field_name, value)
    db.commit()
    db.refresh(search)
    return search


def archive_search(db: Session, search_id: UUID) -> JobSearch:
    """Soft-archive and disable a job search configuration."""
    search = get_search(db, search_id)
    search.is_archived = True
    search.is_active = False
    db.commit()
    db.refresh(search)
    return search
