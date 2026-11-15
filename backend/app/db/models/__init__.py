"""ORM models package exporting all Phase 1-8 tables."""

from app.db.models.application import ApplicationEvent, JobApplication
from app.db.models.company import Company, CompanySource
from app.db.models.job import Job, JobEvaluation, JobSourceReference
from app.db.models.profile import Resume, UserProfile
from app.db.models.search_and_runs import EmailMessage, IngestionRun, JobSearch
from app.db.models.task import Task

__all__ = [
    "ApplicationEvent",
    "Company",
    "CompanySource",
    "EmailMessage",
    "IngestionRun",
    "Job",
    "JobApplication",
    "JobEvaluation",
    "JobSearch",
    "JobSourceReference",
    "Resume",
    "Task",
    "UserProfile",
]
