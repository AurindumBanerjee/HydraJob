"""Score band classification and idempotent internal application task generation."""

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from app.services.matching.eligibility import EligibilityStatus
from app.services.matching.scorer import JobEvaluationResult, RecommendationType

ScoreBandLabel = Literal["EXCELLENT", "GOOD", "REVIEW", "LOW_RELEVANCE", "INELIGIBLE"]


class TaskPolicyThresholds(BaseModel):
    """Configurable thresholds controlling task generation policy."""

    excellent_min: int = Field(default=85, ge=0, le=100)
    good_min: int = Field(default=70, ge=0, le=100)
    review_min: int = Field(default=55, ge=0, le=100)
    allow_uncertain_eligibility: bool = False
    create_review_only_in_review_band: bool = True


class ScoreBandResult(BaseModel):
    """Score band and policy recommendation for a job evaluation."""

    band: ScoreBandLabel
    recommendation: RecommendationType
    qualifies_for_tasks: bool


class TaskTemplate(BaseModel):
    """Idempotent internal task template ready for persistence."""

    title: str
    description: str
    task_type: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    idempotency_key: str


_FULL_TASK_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "Review job description",
        "REVIEW",
        "Verify role responsibilities, requirements, and stated deadline.",
    ),
    (
        "Select resume",
        "RESUME_SELECTION",
        "Confirm or tailor the recommended resume version for this role.",
    ),
    (
        "Prepare application",
        "APPLICATION_PREP",
        "Prepare responses, project highlights, and application materials.",
    ),
    (
        "Submit application",
        "APPLICATION_SUBMIT",
        "Complete and submit the application manually before any stated deadline.",
    ),
)


def classify_score_band(
    overall_score: int,
    eligibility_status: EligibilityStatus,
    thresholds: TaskPolicyThresholds | None = None,
) -> ScoreBandResult:
    """Classify an evaluation score into policy bands and task eligibility."""
    cfg = thresholds or TaskPolicyThresholds()
    if eligibility_status == "INELIGIBLE":
        return ScoreBandResult(
            band="INELIGIBLE",
            recommendation="INELIGIBLE",
            qualifies_for_tasks=False,
        )

    if overall_score >= cfg.excellent_min:
        band: ScoreBandLabel = "EXCELLENT"
        rec: RecommendationType = "HIGH_PRIORITY"
    elif overall_score >= cfg.good_min:
        band = "GOOD"
        rec = "GOOD"
    elif overall_score >= cfg.review_min:
        band = "REVIEW"
        rec = "REVIEW"
    else:
        band = "LOW_RELEVANCE"
        rec = "LOW_RELEVANCE"

    eligibility_ok = eligibility_status == "ELIGIBLE" or (
        cfg.allow_uncertain_eligibility and eligibility_status == "UNCERTAIN"
    )
    qualifies = eligibility_ok and overall_score >= cfg.review_min
    return ScoreBandResult(band=band, recommendation=rec, qualifies_for_tasks=qualifies)


def _task_slug(title: str) -> str:
    return "_".join(title.lower().split())


def generate_application_tasks(
    evaluation: JobEvaluationResult,
    *,
    job_title: str = "",
    company_name: str = "",
    existing_task_keys: Iterable[str] = (),
    existing_task_titles: Iterable[str] = (),
    thresholds: TaskPolicyThresholds | None = None,
) -> list[TaskTemplate]:
    """Generate idempotent internal application tasks only for policy-qualifying jobs."""
    cfg = thresholds or TaskPolicyThresholds()
    band_info = classify_score_band(
        evaluation.overall_score,
        evaluation.eligibility_status,
        thresholds=cfg,
    )
    if not band_info.qualifies_for_tasks:
        return []

    seen_keys = {str(k).strip().lower() for k in existing_task_keys if str(k).strip()}
    seen_titles = {str(t).strip().lower() for t in existing_task_titles if str(t).strip()}

    priority: Literal["HIGH", "MEDIUM", "LOW"] = (
        "HIGH"
        if band_info.band == "EXCELLENT"
        else ("MEDIUM" if band_info.band == "GOOD" else "LOW")
    )

    templates = (
        _FULL_TASK_TEMPLATES[:1]
        if (band_info.band == "REVIEW" and cfg.create_review_only_in_review_band)
        else _FULL_TASK_TEMPLATES
    )

    job_ref = str(evaluation.job_id or f"{company_name}:{job_title}".strip(":") or "unlinked")
    context_suffix = (
        f" ({job_title} at {company_name})".strip() if (job_title or company_name) else ""
    )
    resume_note = (
        f" Suggested resume: {evaluation.recommended_resume_name}."
        if evaluation.recommended_resume_name
        else ""
    )

    created: list[TaskTemplate] = []
    for title, task_type, base_desc in templates:
        idem_key = f"job:{job_ref}:task:{_task_slug(title)}".lower()
        if idem_key in seen_keys or title.lower() in seen_titles:
            continue
        desc = f"{base_desc}{context_suffix}"
        if task_type == "RESUME_SELECTION" and resume_note:
            desc += resume_note
        created.append(
            TaskTemplate(
                title=title,
                description=desc.strip(),
                task_type=task_type,
                priority=priority,
                idempotency_key=idem_key,
            )
        )
        seen_keys.add(idem_key)
        seen_titles.add(title.lower())

    return created
