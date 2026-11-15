"""DB-backed orchestration workflows bridging FastAPI routes and domain services."""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import HydraJobError
from app.db.base import utc_now
from app.db.models import (
    ApplicationEvent,
    Company,
    CompanySource,
    EmailMessage,
    IngestionRun,
    Job,
    JobApplication,
    JobEvaluation,
    JobSearch,
    JobSourceReference,
    Task,
)
from app.db.repositories import crud
from app.schemas.email import SyntheticEmailIngestRequest
from app.services.email import (
    ApplicationMatchCandidate,
    EmailCategory,
    EmailMatchSignal,
    aclassify_email,
    classify_email,
    is_status_regression,
    match_email_to_applications,
)
from app.services.matching import (
    JobRequirementsSnapshot,
    ProfileSnapshot,
    ResumeSnapshot,
    aevaluate_job,
    generate_application_tasks,
)
from app.services.scraping import (
    DiscoveredJobSummary,
    ExistingJobFingerprint,
    ExtractedJobData,
    SSRFValidationError,
    canonicalize_job_url,
    compute_dedup_decision,
    extract_domain,
    extract_job_from_html,
    extract_job_with_ollama,
    get_adapter,
    safe_fetch_url,
    validate_safe_url,
)

logger = logging.getLogger(__name__)

_EMAIL_CATEGORY_TO_APP_STATUS: dict[str, str | None] = {
    EmailCategory.APPLICATION_ACKNOWLEDGEMENT.value: "ACKNOWLEDGED",
    EmailCategory.APPLICATION_RECEIVED.value: "ACKNOWLEDGED",
    EmailCategory.UNDER_REVIEW.value: "UNDER_REVIEW",
    EmailCategory.OA_INVITATION.value: "OA_RECEIVED",
    EmailCategory.ASSESSMENT_REMINDER.value: None,
    EmailCategory.ASSESSMENT_COMPLETED.value: "OA_COMPLETED",
    EmailCategory.TECHNICAL_TEST.value: "TECHNICAL_TEST",
    EmailCategory.INTERVIEW_INVITATION.value: "INTERVIEW_SCHEDULED",
    EmailCategory.INTERVIEW_RESCHEDULE.value: "INTERVIEW_SCHEDULED",
    EmailCategory.INTERVIEW_FEEDBACK.value: "INTERVIEW_COMPLETED",
    EmailCategory.NEXT_ROUND.value: "FURTHER_ROUNDS",
    EmailCategory.OFFER.value: "OFFER_RECEIVED",
    EmailCategory.REJECTION.value: "REJECTED",
    EmailCategory.WITHDRAWAL.value: "WITHDRAWN",
    EmailCategory.DOCUMENT_REQUEST.value: None,
    EmailCategory.INFORMATION_REQUEST.value: None,
    EmailCategory.NON_RECRUITMENT.value: None,
    EmailCategory.UNKNOWN.value: None,
}


def _parse_optional_deadline(raw_value: str | datetime | None) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=UTC)
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _resolve_or_create_company(
    db: Session,
    *,
    company_id: UUID | None = None,
    company_name: str | None = None,
    website: str | None = None,
    industry: str | None = None,
    fallback_url: str | None = None,
) -> Company:
    if company_id is not None:
        return crud.get_company(db, company_id)

    resolved_name = (company_name or "").strip()
    if not resolved_name and fallback_url:
        domain = extract_domain(fallback_url)
        resolved_name = domain or "Unknown Company"
    if not resolved_name:
        resolved_name = "Unknown Company"

    norm = crud.normalize_text(resolved_name)
    existing = db.scalars(select(Company).where(Company.normalized_name == norm)).first()
    if existing is not None:
        return existing

    company = Company(
        name=resolved_name[:200],
        normalized_name=norm[:200],
        website=website,
        industry=industry,
    )
    db.add(company)
    db.flush()
    return company


def _load_existing_fingerprints(db: Session) -> list[ExistingJobFingerprint]:
    jobs = list(db.scalars(select(Job).where(Job.is_archived.is_(False))).all())
    if not jobs:
        return []
    company_map = {
        c.id: c.name for c in db.scalars(select(Company)).all()
    }
    refs = list(db.scalars(select(JobSourceReference)).all())
    refs_by_job: dict[UUID, list[tuple[str, str]]] = {}
    for ref in refs:
        if ref.source_external_id:
            refs_by_job.setdefault(ref.job_id, []).append(
                ("source", ref.source_external_id)
            )

    return [
        ExistingJobFingerprint(
            job_id=str(j.id),
            canonical_url=j.canonical_url,
            external_id=j.external_job_id,
            source_references=refs_by_job.get(j.id, []),
            company=company_map.get(j.company_id),
            title=j.title,
            normalized_title=j.normalized_title,
            location=j.location,
            normalized_location=j.normalized_location,
            description=j.description,
        )
        for j in jobs
    ]


def upsert_extracted_job(
    db: Session,
    *,
    extracted: ExtractedJobData,
    source_url: str,
    canonical_url: str,
    company_id: UUID | None = None,
    source_id: UUID | None = None,
    source_type: str | None = None,
    external_id: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> tuple[Job, bool, bool]:
    """Deduplicate and upsert a Job + JobSourceReference from extracted metadata."""
    now = utc_now()
    ext_id = external_id or extracted.external_job_id
    title = (extracted.title or "Untitled Role").strip()[:300]

    company = _resolve_or_create_company(
        db,
        company_id=company_id,
        company_name=extracted.company,
        fallback_url=source_url,
    )

    fingerprints = _load_existing_fingerprints(db)
    decision = compute_dedup_decision(
        canonical_url=canonical_url,
        source_type=source_type,
        external_id=ext_id,
        company=company.name,
        title=title,
        location=extracted.location,
        description=extracted.description,
        existing_jobs=fingerprints,
    )

    if decision.is_duplicate and decision.matched_job_id:
        existing_job = db.get(Job, UUID(str(decision.matched_job_id)))
        if existing_job is not None:
            changed = False
            if extracted.description and not existing_job.description:
                existing_job.description = extracted.description
                changed = True
            if extracted.required_skills and not existing_job.required_skills:
                existing_job.required_skills = extracted.required_skills
                changed = True
            if extracted.location and not existing_job.location:
                existing_job.location = extracted.location[:200]
                existing_job.normalized_location = crud.normalize_text(extracted.location)[:200]
                changed = True
            if existing_job.missing_scan_count > 0:
                existing_job.missing_scan_count = 0
                changed = True
            existing_job.last_seen_at = now
            if changed:
                existing_job.last_changed_at = now

            existing_ref = db.scalars(
                select(JobSourceReference).where(
                    JobSourceReference.job_id == existing_job.id,
                    JobSourceReference.canonical_url == canonical_url,
                )
            ).first()
            if existing_ref is None:
                db.add(
                    JobSourceReference(
                        job_id=existing_job.id,
                        source_id=source_id,
                        source_external_id=ext_id,
                        original_url=source_url[:1000],
                        canonical_url=canonical_url[:1000],
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                existing_ref.last_seen_at = now
            db.flush()
            return existing_job, False, True

    norm_title = crud.normalize_text(title)[:300]
    norm_loc = crud.normalize_text(extracted.location)[:200] if extracted.location else None

    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=norm_title,
        description=extracted.description,
        location=extracted.location[:200] if extracted.location else None,
        normalized_location=norm_loc,
        country=extracted.country[:120] if extracted.country else None,
        employment_type=extracted.employment_type[:80] if extracted.employment_type else None,
        workplace_type=extracted.workplace_type[:80] if extracted.workplace_type else None,
        experience_requirement=(
            extracted.experience_requirement[:200] if extracted.experience_requirement else None
        ),
        graduation_year_requirement=extracted.graduation_year_requirement,
        degree_requirement=(
            extracted.degree_requirement[:200] if extracted.degree_requirement else None
        ),
        required_skills=list(extracted.required_skills),
        preferred_skills=list(extracted.preferred_skills),
        responsibilities=list(extracted.responsibilities),
        qualifications=list(extracted.qualifications),
        salary=extracted.salary[:200] if extracted.salary else None,
        currency=extracted.currency[:16] if extracted.currency else None,
        application_deadline=_parse_optional_deadline(extracted.application_deadline),
        application_url=(extracted.application_url or source_url)[:1000],
        canonical_url=canonical_url[:1000],
        external_job_id=ext_id[:200] if ext_id else None,
        source_metadata={
            "extraction_method": extracted.extraction_method,
            "extraction_methods_used": extracted.extraction_methods_used,
        },
        raw_extraction_data=raw_payload or extracted.raw_metadata,
        status="ACTIVE" if extracted.title else "NEEDS_REVIEW",
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(job)
    db.flush()

    db.add(
        JobSourceReference(
            job_id=job.id,
            source_id=source_id,
            source_external_id=ext_id,
            original_url=source_url[:1000],
            canonical_url=canonical_url[:1000],
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    db.flush()
    return job, True, False


def _extract_from_raw_payload(
    raw_payload: dict[str, Any] | list[Any],
    url: str,
) -> ExtractedJobData:
    if isinstance(raw_payload, dict) and "title" in raw_payload:
        adapter = get_adapter("generic_json")
        raw_text = json.dumps(raw_payload)
        listings = adapter.parse_listings(raw_text, url)
        if listings:
            first = listings[0]
            return ExtractedJobData(
                company=first.company,
                title=first.title,
                location=first.location,
                employment_type=first.employment_type,
                workplace_type=first.workplace_type,
                description=first.description,
                application_url=first.url,
                external_job_id=first.external_id,
                extraction_method="generic_json",
                extraction_methods_used=["generic_json"],
                raw_metadata=raw_payload,
            )
    return extract_job_from_html(json.dumps(raw_payload), url=url)


async def execute_url_ingestion(
    db: Session,
    *,
    url: str,
    company_id: UUID | None = None,
    source_id: UUID | None = None,
    use_ollama: bool = True,
    html_content: str | None = None,
    raw_payload: dict[str, Any] | list[Any] | None = None,
    existing_run: IngestionRun | None = None,
) -> IngestionRun:
    """Validate, fetch, extract, deduplicate, and persist a single job URL ingestion."""
    offline_fixture = html_content is not None or raw_payload is not None
    try:
        safe_url = validate_safe_url(url, resolve_dns=not offline_fixture)
    except SSRFValidationError as exc:
        raise HydraJobError(
            str(exc),
            code="ssrf_blocked",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    canon_url = canonicalize_job_url(safe_url)
    now = utc_now()

    run = existing_run
    if run is None:
        run = IngestionRun(
            url=safe_url[:1000],
            canonical_url=canon_url[:1000],
            source_id=source_id,
            run_type="URL_INGEST",
            status="RUNNING",
            started_at=now,
        )
        db.add(run)
        db.flush()
    else:
        run.status = "RUNNING"
        run.errors = []
        run.completed_at = None

    try:
        fetched_html = html_content
        final_url = safe_url
        if raw_payload is not None:
            extracted = _extract_from_raw_payload(raw_payload, safe_url)
        else:
            if fetched_html is None:
                fetch_res = await safe_fetch_url(safe_url, timeout=15.0)
                if fetch_res.status_code >= 400:
                    raise RuntimeError(f"Target URL returned HTTP {fetch_res.status_code}")
                fetched_html = fetch_res.text
                final_url = fetch_res.final_url
                canon_url = canonicalize_job_url(final_url)
                run.canonical_url = canon_url[:1000]

            extracted = extract_job_from_html(fetched_html, url=final_url)

        if use_ollama and (
            not extracted.title or not extracted.company or not extracted.required_skills
        ):
            text_for_llm = extracted.description or (fetched_html or "")
            if text_for_llm.strip():
                extracted, _ = await extract_job_with_ollama(
                    text_for_llm,
                    url=final_url,
                    base_data=extracted,
                )

        if not extracted.title:
            run.status = "NEEDS_REVIEW"
            run.errors = ["Could not deterministically extract a job title."]
            run.completed_at = utc_now()
            db.commit()
            db.refresh(run)
            return run

        job, is_new, is_updated = upsert_extracted_job(
            db,
            extracted=extracted,
            source_url=final_url,
            canonical_url=canon_url,
            company_id=company_id,
            source_id=source_id,
            raw_payload=raw_payload if isinstance(raw_payload, dict) else None,
        )

        run.extracted_job_id = job.id
        run.jobs_discovered = 1
        run.jobs_new = 1 if is_new else 0
        run.jobs_updated = 1 if is_updated else 0
        run.status = "COMPLETED"
        run.completed_at = utc_now()
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:  # noqa: BLE001
        logger.warning("URL ingestion failed for %s: %s", canon_url, type(exc).__name__)
        run.status = "FAILED"
        run.errors = [str(exc)]
        run.completed_at = utc_now()
        db.commit()
        db.refresh(run)
        return run


async def evaluate_job_and_create_tasks(
    db: Session,
    *,
    job: Job,
    resume_id: UUID | None = None,
    use_ollama: bool = False,
) -> JobEvaluation:
    """Evaluate a job against the user's profile and create idempotent tasks."""
    profile = crud.get_or_seed_profile(db)
    company = db.get(Company, job.company_id)

    if resume_id is not None:
        selected_resume = crud.get_resume(db, resume_id)
        resume_rows = [selected_resume]
    else:
        resume_rows, _ = crud.list_resumes(db, include_archived=False, limit=50, offset=0)

    work_auths = (
        [profile.work_authorization]
        if profile.work_authorization
        else []
    )
    profile_snapshot = ProfileSnapshot(
        name=profile.name,
        degree=profile.degree,
        branch=profile.branch,
        university=profile.university,
        graduation_year=profile.graduation_year,
        cgpa=profile.cgpa,
        experience_summary=profile.experience_summary,
        skills=list(profile.skills),
        projects=list(profile.projects),
        preferred_roles=list(profile.preferred_roles),
        preferred_locations=list(profile.preferred_locations),
        excluded_locations=list(profile.excluded_locations),
        work_authorizations=work_auths,
    )
    resume_snapshots = [
        ResumeSnapshot(
            id=str(r.id),
            name=r.name,
            skills=list(r.skills),
            extracted_text=r.extracted_text,
            is_preferred=r.is_preferred,
            is_active=r.is_active,
        )
        for r in resume_rows
        if r.is_active and not r.is_archived
    ]
    job_snapshot = JobRequirementsSnapshot(
        job_id=str(job.id),
        title=job.title,
        company=company.name if company else None,
        description=job.description,
        location=job.location,
        country=job.country,
        employment_type=job.employment_type,
        workplace_type=job.workplace_type,
        experience_requirement=job.experience_requirement,
        graduation_year_requirement=job.graduation_year_requirement,
        degree_requirement=job.degree_requirement,
        required_skills=list(job.required_skills),
        preferred_skills=list(job.preferred_skills),
        responsibilities=list(job.responsibilities),
        qualifications=list(job.qualifications),
    )

    result = await aevaluate_job(
        profile=profile_snapshot,
        job=job_snapshot,
        resumes=resume_snapshots,
        use_ollama=use_ollama,
    )

    rec_resume_uuid: UUID | None = None
    if result.recommended_resume_id:
        try:
            rec_resume_uuid = UUID(str(result.recommended_resume_id))
        except ValueError:
            rec_resume_uuid = None

    evaluation = JobEvaluation(
        job_id=job.id,
        profile_id=profile.id,
        recommended_resume_id=rec_resume_uuid,
        eligibility_status=result.eligibility_status,
        overall_score=result.overall_score,
        component_scores=result.component_scores.model_dump(),
        matched_skills=list(result.matched_skills),
        missing_skills=list(result.missing_skills),
        strengths=list(result.strengths),
        concerns=list(result.concerns),
        recommendation=result.recommendation,
        explanation=result.explanation,
        model_name=result.model_name,
        evaluation_version=result.evaluation_version,
        evaluated_at=utc_now(),
    )
    db.add(evaluation)

    existing_tasks = list(
        db.scalars(
            select(Task).where(Task.job_id == job.id, Task.is_archived.is_(False))
        ).all()
    )
    existing_types = {t.task_type for t in existing_tasks}
    existing_titles = {t.title for t in existing_tasks}
    task_templates = generate_application_tasks(
        result,
        job_title=job.title,
        company_name=company.name if company else "",
        existing_task_titles=existing_titles,
    )
    for tpl in task_templates:
        if tpl.task_type in existing_types or tpl.title in existing_titles:
            continue
        db.add(
            Task(
                title=tpl.title[:300],
                description=tpl.description,
                job_id=job.id,
                task_type=tpl.task_type,
                status="PENDING",
                priority=tpl.priority,
            )
        )

    db.commit()
    db.refresh(evaluation)
    return evaluation


def _summary_to_extracted(
    summary: DiscoveredJobSummary,
    *,
    company_name: str,
    adapter_name: str,
) -> ExtractedJobData:
    return ExtractedJobData(
        company=summary.company or company_name,
        title=summary.title,
        location=summary.location,
        employment_type=summary.employment_type,
        workplace_type=summary.workplace_type,
        description=summary.description,
        application_url=summary.url,
        external_job_id=summary.external_id,
        extraction_method=adapter_name,
        extraction_methods_used=[adapter_name],
        raw_metadata=summary.raw_payload,
    )


async def scan_single_source(
    db: Session,
    *,
    source: CompanySource,
    sample_content: str | None = None,
) -> IngestionRun:
    """Scan one career-page source, upsert jobs, and apply the 3-miss closure rule."""
    now = utc_now()
    company = crud.get_company(db, source.company_id)

    run = IngestionRun(
        url=source.career_url,
        canonical_url=source.canonical_url,
        source_id=source.id,
        run_type="SOURCE_SCAN",
        status="RUNNING",
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        adapter = get_adapter(source.adapter_name)
        content = sample_content
        if content is None:
            listing_url = adapter.build_listing_url(source.career_url)
            fetch_res = await safe_fetch_url(listing_url, timeout=15.0)
            if fetch_res.status_code >= 400:
                raise RuntimeError(f"Source returned HTTP {fetch_res.status_code}")
            content = fetch_res.text

        summaries = adapter.parse_listings(
            content,
            source.career_url,
            company_name=company.name,
        )

        seen_job_ids: set[UUID] = set()
        jobs_new = 0
        jobs_updated = 0
        for summary in summaries:
            extracted = _summary_to_extracted(
                summary,
                company_name=company.name,
                adapter_name=adapter.name,
            )
            job, is_new, is_updated = upsert_extracted_job(
                db,
                extracted=extracted,
                source_url=summary.url,
                canonical_url=summary.canonical_url,
                company_id=company.id,
                source_id=source.id,
                source_type=adapter.name,
                external_id=summary.external_id,
                raw_payload=summary.raw_payload,
            )
            seen_job_ids.add(job.id)
            if is_new:
                jobs_new += 1
            elif is_updated:
                jobs_updated += 1

        # Only after a successful scan, increment missing_scan_count on jobs linked to this source
        # that were absent from this scan; mark CLOSED only once missing_scan_count >= 3.
        linked_job_ids = set(
            db.scalars(
                select(JobSourceReference.job_id).where(
                    JobSourceReference.source_id == source.id
                )
            ).all()
        )
        for linked_id in linked_job_ids - seen_job_ids:
            missing_job = db.get(Job, linked_id)
            if missing_job is not None and not missing_job.is_archived and missing_job.is_active:
                missing_job.missing_scan_count += 1
                if missing_job.missing_scan_count >= 3:
                    missing_job.status = "CLOSED"
                    missing_job.is_active = False
                    missing_job.last_changed_at = utc_now()

        source.consecutive_failures = 0
        source.last_error = None
        source.last_checked_at = now
        source.last_successful_scan_at = now

        run.jobs_discovered = len(summaries)
        run.jobs_new = jobs_new
        run.jobs_updated = jobs_updated
        run.status = "COMPLETED"
        run.completed_at = utc_now()
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:  # noqa: BLE001
        logger.warning("Source scan failed for %s: %s", source.id, type(exc).__name__)
        source.consecutive_failures += 1
        source.last_checked_at = now
        source.last_error = str(exc)

        run.status = "FAILED"
        run.errors = [str(exc)]
        run.completed_at = utc_now()
        db.commit()
        db.refresh(run)
        return run


def _job_matches_search(job: Job, company_name: str, search: JobSearch) -> bool:
    haystack = " ".join(
        [
            job.title or "",
            job.description or "",
            " ".join(job.required_skills),
            " ".join(job.preferred_skills),
        ]
    ).lower()

    if search.keywords and not any(kw.lower() in haystack for kw in search.keywords):
        return False

    if search.roles:
        title_l = (job.title or "").lower()
        if not any(r.lower() in title_l or r.lower() in haystack for r in search.roles):
            return False

    if search.locations:
        loc_l = (job.location or "").lower()
        workplace_l = (job.workplace_type or "").lower()
        if not any(
            loc.lower() in loc_l or (loc.lower() == "remote" and workplace_l == "remote")
            for loc in search.locations
        ):
            return False

    if search.employment_types:
        emp_l = (job.employment_type or "").lower()
        if not any(et.lower() in emp_l for et in search.employment_types):
            return False

    if (
        search.graduation_year is not None
        and job.graduation_year_requirement is not None
        and job.graduation_year_requirement != search.graduation_year
    ):
        return False

    comp_l = company_name.lower()
    if search.included_companies and not any(
        c.lower() in comp_l for c in search.included_companies
    ):
        return False
    if search.excluded_companies and any(
        c.lower() in comp_l for c in search.excluded_companies
    ):
        return False

    return True


async def execute_search_run(db: Session, *, search: JobSearch) -> IngestionRun:
    """Filter active jobs by JobSearch criteria, evaluate unscored jobs, and record run."""
    now = utc_now()
    run = IngestionRun(
        run_type="SEARCH_RUN",
        status="RUNNING",
        started_at=now,
    )
    db.add(run)
    db.flush()

    active_jobs = list(
        db.scalars(
            select(Job).where(Job.is_archived.is_(False), Job.is_active.is_(True))
        ).all()
    )
    companies = {c.id: c.name for c in db.scalars(select(Company)).all()}

    matched_count = 0
    for job in active_jobs:
        company_name = companies.get(job.company_id, "")
        if not _job_matches_search(job, company_name, search):
            continue

        latest_eval = db.scalars(
            select(JobEvaluation)
            .where(JobEvaluation.job_id == job.id)
            .order_by(JobEvaluation.evaluated_at.desc())
        ).first()
        if latest_eval is None:
            latest_eval = await evaluate_job_and_create_tasks(db, job=job, use_ollama=False)

        if (
            search.min_match_score is not None
            and latest_eval.overall_score < search.min_match_score
        ):
            continue
        matched_count += 1

    run.jobs_discovered = matched_count
    run.status = "COMPLETED"
    run.completed_at = utc_now()
    db.commit()
    db.refresh(run)
    return run


def _extract_sender_domain(sender: str) -> str:
    addr = sender.strip().rstrip(">")
    if "@" in addr:
        return addr.rsplit("@", 1)[-1].strip().lower()
    return ""


async def process_email_message(
    db: Session,
    *,
    payload: SyntheticEmailIngestRequest,
    use_ollama: bool = False,
) -> EmailMessage:
    """Idempotently classify, match, and optionally update application status from email."""
    existing = db.scalars(
        select(EmailMessage).where(
            EmailMessage.gmail_message_id == payload.gmail_message_id
        )
    ).first()
    if existing is not None:
        return existing

    sender_domain = _extract_sender_domain(payload.sender)
    snippet = payload.snippet or (payload.body or "")[:500]

    if use_ollama:
        classification = await aclassify_email(
            subject=payload.subject,
            snippet=snippet,
            sender_domain=sender_domain,
            use_ollama=True,
        )
    else:
        classification = classify_email(
            subject=payload.subject,
            snippet=snippet,
            sender_domain=sender_domain,
        )

    apps = list(
        db.scalars(
            select(JobApplication).where(JobApplication.is_archived.is_(False))
        ).all()
    )
    jobs = {j.id: j for j in db.scalars(select(Job)).all()}
    companies = {c.id: c for c in db.scalars(select(Company)).all()}

    candidates: list[ApplicationMatchCandidate] = []
    for app in apps:
        job = jobs.get(app.job_id)
        company = companies.get(job.company_id) if job else None
        candidates.append(
            ApplicationMatchCandidate(
                application_id=str(app.id),
                job_id=str(app.job_id),
                company_name=company.name if company else "",
                company_domain=(
                    extract_domain(company.website) if company and company.website else None
                ),
                job_title=job.title if job else "",
                current_status=app.status,
                thread_id=app.thread_id,
                is_archived=app.is_archived,
            )
        )

    signal = EmailMatchSignal(
        gmail_message_id=payload.gmail_message_id,
        thread_id=payload.thread_id,
        sender=payload.sender,
        sender_domain=sender_domain,
        subject=payload.subject,
        snippet=snippet,
    )
    match_res = match_email_to_applications(
        signal=signal,
        classification=classification,
        candidates=candidates,
    )

    matched_app_uuid: UUID | None = None
    if match_res.matched_application_id is not None:
        matched_app_uuid = UUID(str(match_res.matched_application_id))

    email_record = EmailMessage(
        gmail_message_id=payload.gmail_message_id,
        thread_id=payload.thread_id,
        sender=payload.sender[:320],
        sender_domain=sender_domain[:200] if sender_domain else None,
        subject=payload.subject[:500],
        snippet=snippet,
        received_at=payload.received_at or utc_now(),
        classification=classification.category.value,
        confidence=match_res.overall_confidence or classification.confidence,
        matched_application_id=matched_app_uuid,
        status_applied=False,
        needs_review=match_res.needs_review,
        review_notes=match_res.reason,
    )
    db.add(email_record)
    db.flush()

    if matched_app_uuid is not None:
        app_row = db.get(JobApplication, matched_app_uuid)
        if app_row is not None:
            if match_res.should_apply_status and match_res.proposed_status:
                prev_status = app_row.status
                app_row.status = match_res.proposed_status
                email_record.status_applied = True
                db.add(
                    ApplicationEvent(
                        application_id=app_row.id,
                        event_type="EMAIL_STATUS_UPDATE",
                        previous_status=prev_status,
                        new_status=match_res.proposed_status,
                        source="EMAIL",
                        description=(
                            f"Email classified as {classification.category.value}: "
                            f"{payload.subject[:200]}"
                        ),
                        confidence=match_res.overall_confidence,
                        needs_review=False,
                        email_message_id=email_record.id,
                        occurred_at=utc_now(),
                    )
                )
            elif match_res.decision in {
                "EVENT_ONLY",
                "NEEDS_REVIEW",
                "NO_UPDATE_REGRESSION_BLOCKED",
            }:
                db.add(
                    ApplicationEvent(
                        application_id=app_row.id,
                        event_type="EMAIL_EVENT",
                        previous_status=app_row.status,
                        new_status=app_row.status,
                        source="EMAIL",
                        description=(
                            f"Email ({classification.category.value}): {match_res.reason}"
                        ),
                        confidence=match_res.overall_confidence,
                        needs_review=match_res.needs_review,
                        email_message_id=email_record.id,
                        occurred_at=utc_now(),
                    )
                )

    db.commit()
    db.refresh(email_record)
    return email_record


def review_email_and_optionally_apply(
    db: Session,
    *,
    email_id: UUID,
    classification: str | None = None,
    matched_application_id: UUID | None = None,
    apply_status_update: bool = False,
    needs_review: bool = False,
    review_notes: str | None = None,
) -> EmailMessage:
    """Manually confirm or correct an email classification/link and optionally update status."""
    email_row = db.get(EmailMessage, email_id)
    if email_row is None:
        raise HydraJobError(
            "Email message not found.",
            code="email_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if classification is not None:
        email_row.classification = classification
    if matched_application_id is not None:
        crud.get_application(db, matched_application_id)
        email_row.matched_application_id = matched_application_id
    email_row.needs_review = needs_review
    if review_notes is not None:
        email_row.review_notes = review_notes

    if apply_status_update and email_row.matched_application_id is not None:
        app_row = crud.get_application(db, email_row.matched_application_id)
        proposed = _EMAIL_CATEGORY_TO_APP_STATUS.get(email_row.classification)
        if proposed is None:
            raise HydraJobError(
                f"Classification '{email_row.classification}' does not map to a status update.",
                code="no_status_mapping",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if is_status_regression(app_row.status, proposed):
            raise HydraJobError(
                f"Cannot regress application status from {app_row.status} to {proposed}.",
                code="status_regression_blocked",
                status_code=status.HTTP_409_CONFLICT,
            )
        prev_status = app_row.status
        app_row.status = proposed
        email_row.status_applied = True
        db.add(
            ApplicationEvent(
                application_id=app_row.id,
                event_type="EMAIL_MANUAL_REVIEW",
                previous_status=prev_status,
                new_status=proposed,
                source="EMAIL_MANUAL_REVIEW",
                description=review_notes or f"Manual review applied {email_row.classification}",
                confidence=email_row.confidence,
                needs_review=False,
                email_message_id=email_row.id,
                occurred_at=utc_now(),
            )
        )

    db.commit()
    db.refresh(email_row)
    return email_row
