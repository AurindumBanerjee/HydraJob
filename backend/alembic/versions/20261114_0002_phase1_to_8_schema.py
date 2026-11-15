"""Create Phase 1 to 8 domain tables.

Revision ID: 20261114_0002
Revises: 20261114_0001
Create Date: 2026-11-14 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261114_0002"
down_revision: str | Sequence[str] | None = "20261114_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create core HydraJob domain tables."""
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("education", sa.Text(), nullable=True),
        sa.Column("degree", sa.String(length=120), nullable=True),
        sa.Column("branch", sa.String(length=120), nullable=True),
        sa.Column("university", sa.String(length=200), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("cgpa", sa.Float(), nullable=True),
        sa.Column("experience_summary", sa.Text(), nullable=True),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("preferred_roles", sa.JSON(), nullable=False),
        sa.Column("preferred_locations", sa.JSON(), nullable=False),
        sa.Column("excluded_locations", sa.JSON(), nullable=False),
        sa.Column("work_authorization", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_profiles")),
    )

    op.create_table(
        "resumes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("file_type", sa.String(length=50), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resumes")),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_index(
        op.f("ix_companies_normalized_name"),
        "companies",
        ["normalized_name"],
        unique=True,
    )

    op.create_table(
        "company_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("career_url", sa.String(length=1000), nullable=False),
        sa.Column("canonical_url", sa.String(length=1000), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("adapter_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_sources_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_sources")),
    )
    op.create_index(
        op.f("ix_company_sources_canonical_url"),
        "company_sources",
        ["canonical_url"],
        unique=True,
    )
    op.create_index(
        op.f("ix_company_sources_company_id"),
        "company_sources",
        ["company_id"],
        unique=False,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("normalized_title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("normalized_location", sa.String(length=200), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("employment_type", sa.String(length=80), nullable=True),
        sa.Column("workplace_type", sa.String(length=80), nullable=True),
        sa.Column("experience_requirement", sa.String(length=200), nullable=True),
        sa.Column("graduation_year_requirement", sa.Integer(), nullable=True),
        sa.Column("degree_requirement", sa.String(length=200), nullable=True),
        sa.Column("required_skills", sa.JSON(), nullable=False),
        sa.Column("preferred_skills", sa.JSON(), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False),
        sa.Column("qualifications", sa.JSON(), nullable=False),
        sa.Column("salary", sa.String(length=200), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_url", sa.String(length=1000), nullable=True),
        sa.Column("canonical_url", sa.String(length=1000), nullable=True),
        sa.Column("external_job_id", sa.String(length=200), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("raw_extraction_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("missing_scan_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_jobs_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_canonical_url"), "jobs", ["canonical_url"], unique=True)
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_jobs_external_job_id"), "jobs", ["external_job_id"], unique=False)
    op.create_index(
        op.f("ix_jobs_normalized_location"),
        "jobs",
        ["normalized_location"],
        unique=False,
    )
    op.create_index(op.f("ix_jobs_normalized_title"), "jobs", ["normalized_title"], unique=False)

    op.create_table(
        "job_source_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_external_id", sa.String(length=200), nullable=True),
        sa.Column("original_url", sa.String(length=1000), nullable=False),
        sa.Column("canonical_url", sa.String(length=1000), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_source_references_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["company_sources.id"],
            name=op.f("fk_job_source_references_source_id_company_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_source_references")),
    )
    op.create_index(
        op.f("ix_job_source_references_canonical_url"),
        "job_source_references",
        ["canonical_url"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_source_references_job_id"),
        "job_source_references",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_source_references_source_id"),
        "job_source_references",
        ["source_id"],
        unique=False,
    )

    op.create_table(
        "job_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("recommended_resume_id", sa.Uuid(), nullable=True),
        sa.Column("eligibility_status", sa.String(length=32), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("component_scores", sa.JSON(), nullable=False),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("concerns", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("evaluation_version", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_evaluations_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["user_profiles.id"],
            name=op.f("fk_job_evaluations_profile_id_user_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recommended_resume_id"],
            ["resumes.id"],
            name=op.f("fk_job_evaluations_recommended_resume_id_resumes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_evaluations")),
    )
    op.create_index(
        op.f("ix_job_evaluations_job_id"),
        "job_evaluations",
        ["job_id"],
        unique=False,
    )

    op.create_table(
        "job_applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("selected_resume_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("eligibility_status", sa.String(length=32), nullable=True),
        sa.Column("application_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("thread_id", sa.String(length=200), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_applications_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_resume_id"],
            ["resumes.id"],
            name=op.f("fk_job_applications_selected_resume_id_resumes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_applications")),
    )
    op.create_index(
        op.f("ix_job_applications_job_id"),
        "job_applications",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_applications_status"),
        "job_applications",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_applications_thread_id"),
        "job_applications",
        ["thread_id"],
        unique=False,
    )

    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("email_message_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["job_applications.id"],
            name=op.f("fk_application_events_application_id_job_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        op.f("ix_application_events_application_id"),
        "application_events",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_events_occurred_at"),
        "application_events",
        ["occurred_at"],
        unique=False,
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("external_task_id", sa.String(length=200), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["job_applications.id"],
            name=op.f("fk_tasks_application_id_job_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_tasks_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_application_id"), "tasks", ["application_id"], unique=False)
    op.create_index(op.f("ix_tasks_job_id"), "tasks", ["job_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)

    op.create_table(
        "job_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("remote_preference", sa.String(length=64), nullable=True),
        sa.Column("employment_types", sa.JSON(), nullable=False),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("experience_level", sa.String(length=64), nullable=True),
        sa.Column("included_companies", sa.JSON(), nullable=False),
        sa.Column("excluded_companies", sa.JSON(), nullable=False),
        sa.Column("min_match_score", sa.Integer(), nullable=True),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_searches")),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("canonical_url", sa.String(length=1000), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extracted_job_id", sa.Uuid(), nullable=True),
        sa.Column("jobs_discovered", sa.Integer(), nullable=False),
        sa.Column("jobs_new", sa.Integer(), nullable=False),
        sa.Column("jobs_updated", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["extracted_job_id"],
            ["jobs.id"],
            name=op.f("fk_ingestion_runs_extracted_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["company_sources.id"],
            name=op.f("fk_ingestion_runs_source_id_company_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        op.f("ix_ingestion_runs_canonical_url"),
        "ingestion_runs",
        ["canonical_url"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_runs_source_id"),
        "ingestion_runs",
        ["source_id"],
        unique=False,
    )
    op.create_index(op.f("ix_ingestion_runs_status"), "ingestion_runs", ["status"], unique=False)

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=200), nullable=False),
        sa.Column("thread_id", sa.String(length=200), nullable=True),
        sa.Column("sender", sa.String(length=320), nullable=False),
        sa.Column("sender_domain", sa.String(length=200), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("matched_application_id", sa.Uuid(), nullable=True),
        sa.Column("status_applied", sa.Boolean(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["matched_application_id"],
            ["job_applications.id"],
            name=op.f("fk_email_messages_matched_application_id_job_applications"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_messages")),
    )
    op.create_index(
        op.f("ix_email_messages_gmail_message_id"),
        "email_messages",
        ["gmail_message_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_email_messages_matched_application_id"),
        "email_messages",
        ["matched_application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_messages_received_at"),
        "email_messages",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_messages_sender_domain"),
        "email_messages",
        ["sender_domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_messages_thread_id"),
        "email_messages",
        ["thread_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop Phase 1 to 8 domain tables in reverse dependency order."""
    op.drop_index(op.f("ix_email_messages_thread_id"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_sender_domain"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_received_at"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_matched_application_id"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_gmail_message_id"), table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index(op.f("ix_ingestion_runs_status"), table_name="ingestion_runs")
    op.drop_index(op.f("ix_ingestion_runs_source_id"), table_name="ingestion_runs")
    op.drop_index(op.f("ix_ingestion_runs_canonical_url"), table_name="ingestion_runs")
    op.drop_table("ingestion_runs")

    op.drop_table("job_searches")

    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_job_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_application_id"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_application_events_occurred_at"), table_name="application_events")
    op.drop_index(op.f("ix_application_events_application_id"), table_name="application_events")
    op.drop_table("application_events")

    op.drop_index(op.f("ix_job_applications_thread_id"), table_name="job_applications")
    op.drop_index(op.f("ix_job_applications_status"), table_name="job_applications")
    op.drop_index(op.f("ix_job_applications_job_id"), table_name="job_applications")
    op.drop_table("job_applications")

    op.drop_index(op.f("ix_job_evaluations_job_id"), table_name="job_evaluations")
    op.drop_table("job_evaluations")

    op.drop_index(op.f("ix_job_source_references_source_id"), table_name="job_source_references")
    op.drop_index(op.f("ix_job_source_references_job_id"), table_name="job_source_references")
    op.drop_index(
        op.f("ix_job_source_references_canonical_url"),
        table_name="job_source_references",
    )
    op.drop_table("job_source_references")

    op.drop_index(op.f("ix_jobs_normalized_title"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_normalized_location"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_external_job_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_canonical_url"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(op.f("ix_company_sources_company_id"), table_name="company_sources")
    op.drop_index(op.f("ix_company_sources_canonical_url"), table_name="company_sources")
    op.drop_table("company_sources")

    op.drop_index(op.f("ix_companies_normalized_name"), table_name="companies")
    op.drop_table("companies")

    op.drop_table("resumes")
    op.drop_table("user_profiles")
