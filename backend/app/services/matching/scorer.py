"""Weighted profile-to-job scoring, resume recommendation, and Ollama integration."""

import re
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.llm.ollama_client import OllamaClient
from app.services.llm.prompts import PROMPT_VERSION, build_job_evaluation_prompt
from app.services.matching.eligibility import (
    EligibilityResult,
    EligibilityStatus,
    JobRequirementsSnapshot,
    ProfileSnapshot,
    ResumeSnapshot,
    evaluate_eligibility,
)
from app.services.scraping.extractors import extract_skills_from_text

EVALUATION_VERSION = "v1.0"

SCORE_WEIGHTS: dict[str, float] = {
    "eligibility": 0.30,
    "technical": 0.30,
    "experience": 0.20,
    "role_relevance": 0.10,
    "location": 0.10,
}

RecommendationType = Literal[
    "HIGH_PRIORITY",
    "GOOD",
    "REVIEW",
    "LOW_RELEVANCE",
    "INELIGIBLE",
]

_SENIOR_DISQUALIFIERS = (
    "staff engineer",
    "principal",
    "director",
    "vp ",
    "vice president",
    "distinguished",
    "architect",
    "senior manager",
)


class ComponentScores(BaseModel):
    """Five weighted scoring dimensions, each bounded 0..100."""

    eligibility: int = Field(ge=0, le=100)
    technical: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    role_relevance: int = Field(ge=0, le=100)
    location: int = Field(ge=0, le=100)


class OllamaJobEvaluationSchema(BaseModel):
    """Validated JSON schema returned by Ollama during optional evaluation refinement."""

    technical_score: int = Field(ge=0, le=100)
    experience_score: int = Field(ge=0, le=100)
    role_relevance_score: int = Field(ge=0, le=100)
    location_score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    explanation: str


class JobEvaluationResult(BaseModel):
    """Complete structured job evaluation output with evidence and model provenance."""

    job_id: str | int | None = None
    eligibility_status: EligibilityStatus
    eligibility_details: EligibilityResult
    overall_score: int = Field(ge=0, le=100)
    component_scores: ComponentScores
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendation: RecommendationType
    recommended_resume_id: str | int | None = None
    recommended_resume_name: str | None = None
    explanation: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    model_name: str
    evaluation_version: str = EVALUATION_VERSION
    used_fallback: bool = False


def compute_weighted_score(components: ComponentScores) -> int:
    """Compute Score = round(0.30*E + 0.30*T + 0.20*P + 0.10*R + 0.10*L)."""
    raw = (
        SCORE_WEIGHTS["eligibility"] * components.eligibility
        + SCORE_WEIGHTS["technical"] * components.technical
        + SCORE_WEIGHTS["experience"] * components.experience
        + SCORE_WEIGHTS["role_relevance"] * components.role_relevance
        + SCORE_WEIGHTS["location"] * components.location
    )
    return max(0, min(100, round(raw)))


def _normalize_skill_set(skills: Sequence[str]) -> dict[str, str]:
    """Map lowercase canonical skill key -> display label."""
    mapping: dict[str, str] = {}
    for skill in skills:
        cleaned = re.sub(r"\s+", " ", str(skill)).strip()
        if cleaned:
            mapping.setdefault(cleaned.lower(), cleaned)
    return mapping


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#]{2,}", text.lower())}


def recommend_best_resume(
    job: JobRequirementsSnapshot,
    resumes: Sequence[ResumeSnapshot],
    profile: ProfileSnapshot,
) -> tuple[ResumeSnapshot | None, dict[str, int]]:
    """Select the active resume version with strongest skill & text overlap against the job."""
    active_resumes = [r for r in resumes if r.is_active]
    if not active_resumes:
        return None, {}

    job_skills = _normalize_skill_set([*job.required_skills, *job.preferred_skills])
    if not job_skills:
        extracted = extract_skills_from_text(
            " ".join([job.title, job.description or "", *job.qualifications])
        )
        job_skills = _normalize_skill_set(extracted)

    job_tokens = _tokenize(
        " ".join(
            [
                job.title,
                job.description or "",
                *job.responsibilities,
                *job.qualifications,
            ]
        )
    )

    scores: dict[str, int] = {}
    best_resume: ResumeSnapshot | None = None
    best_tuple: tuple[int, int, bool] = (-1, -1, False)

    for resume in active_resumes:
        resume_skills = _normalize_skill_set(
            [*resume.skills, *extract_skills_from_text(resume.extracted_text or "")]
        )
        skill_hits = len(set(job_skills) & set(resume_skills))
        text_tokens = _tokenize(f"{resume.name} {resume.extracted_text or ''}")
        token_hits = len(job_tokens & text_tokens)

        rank_key = (skill_hits, token_hits, resume.is_preferred)
        scores[str(resume.id or resume.name)] = skill_hits * 10 + token_hits
        if rank_key > best_tuple:
            best_tuple = rank_key
            best_resume = resume

    return best_resume, scores


def _score_eligibility_component(eligibility: EligibilityResult) -> int:
    if eligibility.status == "INELIGIBLE":
        return 0
    if eligibility.status == "ELIGIBLE":
        return 100 if not eligibility.missing_requirements else 90
    if eligibility.status == "NOT_EVALUATED":
        return 45
    # UNCERTAIN
    pass_count = len(eligibility.passed_conditions)
    uncertain_count = len(eligibility.uncertain_conditions)
    base = 60 + min(20, pass_count * 6) - min(20, uncertain_count * 8)
    return max(35, min(75, base))


def _score_technical_component(
    profile: ProfileSnapshot,
    best_resume: ResumeSnapshot | None,
    job: JobRequirementsSnapshot,
) -> tuple[int, list[str], list[str]]:
    candidate_skills = _normalize_skill_set(profile.skills)
    if best_resume is not None:
        candidate_skills.update(_normalize_skill_set(best_resume.skills))
        if best_resume.extracted_text:
            candidate_skills.update(
                _normalize_skill_set(extract_skills_from_text(best_resume.extracted_text))
            )

    req_map = _normalize_skill_set(job.required_skills)
    pref_map = _normalize_skill_set(job.preferred_skills)

    if not req_map and not pref_map:
        inferred = extract_skills_from_text(
            " ".join([job.title, job.description or "", *job.qualifications])
        )
        req_map = _normalize_skill_set(inferred)

    if not req_map and not pref_map:
        return 50, [], []

    matched_req = [label for key, label in req_map.items() if key in candidate_skills]
    missing_req = [label for key, label in req_map.items() if key not in candidate_skills]
    matched_pref = [label for key, label in pref_map.items() if key in candidate_skills]
    missing_pref = [label for key, label in pref_map.items() if key not in candidate_skills]

    req_ratio = (len(matched_req) / len(req_map)) if req_map else 1.0
    pref_ratio = (len(matched_pref) / len(pref_map)) if pref_map else 1.0

    if req_map and pref_map:
        score = round(100 * (0.75 * req_ratio + 0.25 * pref_ratio))
    elif req_map:
        score = round(100 * req_ratio)
    else:
        score = round(100 * pref_ratio)

    matched = list(dict.fromkeys([*matched_req, *matched_pref]))
    missing = list(dict.fromkeys([*missing_req, *missing_pref]))
    return max(0, min(100, score)), matched, missing


def _score_experience_component(
    profile: ProfileSnapshot,
    best_resume: ResumeSnapshot | None,
    job: JobRequirementsSnapshot,
) -> int:
    cand_corpus = " ".join(
        [
            profile.experience_summary or "",
            *profile.projects,
            *profile.skills,
            best_resume.extracted_text or "" if best_resume else "",
        ]
    )
    cand_tokens = _tokenize(cand_corpus)
    job_corpus = " ".join(
        [
            job.title,
            job.description or "",
            *job.responsibilities,
            *job.qualifications,
        ]
    )
    job_tokens = _tokenize(job_corpus) - {
        "the",
        "and",
        "for",
        "with",
        "you",
        "will",
        "are",
        "our",
        "that",
        "this",
        "from",
        "have",
        "work",
        "team",
    }
    if not cand_tokens or not job_tokens:
        return 45

    overlap = len(cand_tokens & job_tokens)
    # Saturate smoothly around 12 meaningful overlapping domain/project tokens.
    ratio = min(1.0, overlap / max(6, min(14, len(job_tokens) // 2 + 4)))
    return max(20, min(98, round(30 + 68 * ratio)))


def _score_role_relevance(profile: ProfileSnapshot, job: JobRequirementsSnapshot) -> int:
    title_lower = (job.title or "").lower()
    if any(disq in title_lower for disq in _SENIOR_DISQUALIFIERS):
        return 20

    if not profile.preferred_roles:
        return 60

    title_tokens = _tokenize(job.title)
    best_overlap = 0.0
    for role in profile.preferred_roles:
        role_lower = role.lower()
        if role_lower in title_lower or title_lower in role_lower:
            return 95
        role_tokens = _tokenize(role)
        if role_tokens:
            overlap = len(title_tokens & role_tokens) / len(role_tokens)
            best_overlap = max(best_overlap, overlap)

    return max(25, min(95, round(30 + 65 * best_overlap)))


def _score_location_component(eligibility: EligibilityResult) -> int:
    loc_check = next((c for c in eligibility.checks if c.condition == "location"), None)
    if loc_check is None:
        return 50
    if loc_check.status == "FAIL":
        return 0
    if loc_check.status == "PASS":
        return 100
    if loc_check.status == "UNCERTAIN":
        return 40
    return 55


def _recommendation_for_score(
    score: int,
    eligibility_status: EligibilityStatus,
) -> RecommendationType:
    if eligibility_status == "INELIGIBLE":
        return "INELIGIBLE"
    if score >= 85:
        return "HIGH_PRIORITY"
    if score >= 70:
        return "GOOD"
    if score >= 55:
        return "REVIEW"
    return "LOW_RELEVANCE"


def _apply_ineligible_override(
    raw_score: int,
    eligibility_status: EligibilityStatus,
) -> tuple[int, RecommendationType]:
    """Mandatory INELIGIBLE overrides high relevance scores and forces INELIGIBLE."""
    if eligibility_status == "INELIGIBLE":
        capped_score = min(raw_score, 40)
        return capped_score, "INELIGIBLE"
    return raw_score, _recommendation_for_score(raw_score, eligibility_status)


def evaluate_job(
    *,
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    resumes: Sequence[ResumeSnapshot] = (),
    model_name: str = "deterministic-rules",
) -> JobEvaluationResult:
    """Deterministically evaluate a job posting against a user profile and resumes."""
    eligibility = evaluate_eligibility(profile, job)
    best_resume, resume_scores = recommend_best_resume(job, resumes, profile)

    e_score = _score_eligibility_component(eligibility)
    t_score, matched_skills, missing_skills = _score_technical_component(profile, best_resume, job)
    p_score = _score_experience_component(profile, best_resume, job)
    r_score = _score_role_relevance(profile, job)
    l_score = _score_location_component(eligibility)

    components = ComponentScores(
        eligibility=e_score,
        technical=t_score,
        experience=p_score,
        role_relevance=r_score,
        location=l_score,
    )
    raw_score = compute_weighted_score(components)
    final_score, recommendation = _apply_ineligible_override(raw_score, eligibility.status)

    strengths: list[str] = []
    concerns: list[str] = []

    if eligibility.status == "ELIGIBLE":
        strengths.append("Satisfies all stated mandatory eligibility conditions.")
    elif eligibility.status == "INELIGIBLE":
        for chk in eligibility.checks:
            if chk.status == "FAIL":
                concerns.append(chk.reason)
    elif eligibility.status in {"UNCERTAIN", "NOT_EVALUATED"}:
        concerns.append(eligibility.summary)

    if matched_skills:
        strengths.append(f"Matched skills: {', '.join(matched_skills[:8])}.")
    if missing_skills:
        concerns.append(f"Missing/unconfirmed skills: {', '.join(missing_skills[:8])}.")
    if best_resume is not None:
        strengths.append(f"Best matching resume: {best_resume.name}.")

    explanation = (
        f"Eligibility: {eligibility.status}. Weighted score: {final_score}/100 "
        f"(E={e_score}, T={t_score}, P={p_score}, R={r_score}, L={l_score}). "
        f"Recommendation: {recommendation}."
    )
    if eligibility.status == "INELIGIBLE" and raw_score >= 55:
        explanation += (
            f" High skill/role relevance (raw {raw_score}/100) was overridden by mandatory "
            "ineligibility."
        )

    return JobEvaluationResult(
        job_id=job.job_id,
        eligibility_status=eligibility.status,
        eligibility_details=eligibility,
        overall_score=final_score,
        component_scores=components,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        strengths=strengths,
        concerns=concerns,
        recommendation=recommendation,
        recommended_resume_id=best_resume.id if best_resume else None,
        recommended_resume_name=best_resume.name if best_resume else None,
        explanation=explanation,
        evidence={
            "raw_weighted_score": raw_score,
            "ineligible_override_applied": eligibility.status == "INELIGIBLE",
            "weights": SCORE_WEIGHTS,
            "resume_overlap_scores": resume_scores,
            "missing_requirements": eligibility.missing_requirements,
        },
        model_name=model_name,
        evaluation_version=EVALUATION_VERSION,
        used_fallback=False,
    )


async def aevaluate_job(
    *,
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    resumes: Sequence[ResumeSnapshot] = (),
    ollama_client: OllamaClient | None = None,
    use_ollama: bool = False,
) -> JobEvaluationResult:
    """Evaluate a job with deterministic eligibility gate and optional Ollama scoring refinement."""
    baseline = evaluate_job(profile=profile, job=job, resumes=resumes)
    if not use_ollama:
        return baseline

    client = ollama_client or OllamaClient()
    profile_summary = (
        f"Degree: {profile.degree or 'unknown'} | Branch: {profile.branch or 'unknown'} | "
        f"Grad Year: {profile.graduation_year or 'unknown'} | CGPA: {profile.cgpa or 'unknown'}\n"
        f"Experience ({profile.experience_years} yrs): {profile.experience_summary or ''}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Projects: {', '.join(profile.projects)}\n"
        f"Preferred Roles: {', '.join(profile.preferred_roles)}\n"
        f"Preferred Locations: {', '.join(profile.preferred_locations)}"
    )
    job_summary = (
        f"Title: {job.title} | Company: {job.company or 'unknown'} | "
        f"Location: {job.location or 'unknown'} | Workplace: {job.workplace_type or 'unknown'}\n"
        f"Required Skills: {', '.join(job.required_skills)}\n"
        f"Preferred Skills: {', '.join(job.preferred_skills)}\n"
        f"Qualifications: {' | '.join(job.qualifications)}\n"
        f"Description: {job.description or ''}"
    )
    prompt_spec = build_job_evaluation_prompt(
        profile_summary=profile_summary,
        job_summary=job_summary,
        eligibility_status=baseline.eligibility_status,
        version=PROMPT_VERSION,
    )

    fallback_schema = OllamaJobEvaluationSchema(
        technical_score=baseline.component_scores.technical,
        experience_score=baseline.component_scores.experience,
        role_relevance_score=baseline.component_scores.role_relevance,
        location_score=baseline.component_scores.location,
        matched_skills=baseline.matched_skills,
        missing_skills=baseline.missing_skills,
        strengths=baseline.strengths,
        concerns=baseline.concerns,
        explanation=baseline.explanation,
    )

    llm_resp = await client.agenerate_structured(
        prompt=prompt_spec.user_prompt,
        system_prompt=prompt_spec.system_prompt,
        response_model=OllamaJobEvaluationSchema,
        fallback_factory=lambda: fallback_schema,
        prompt_version=prompt_spec.version,
    )

    if llm_resp.used_fallback:
        baseline.used_fallback = True
        baseline.model_name = f"{baseline.model_name} (ollama-fallback)"
        baseline.evidence["ollama_error"] = llm_resp.error
        return baseline

    components = ComponentScores(
        eligibility=baseline.component_scores.eligibility,
        technical=llm_resp.data.technical_score,
        experience=llm_resp.data.experience_score,
        role_relevance=llm_resp.data.role_relevance_score,
        location=llm_resp.data.location_score,
    )
    raw_score = compute_weighted_score(components)
    final_score, recommendation = _apply_ineligible_override(
        raw_score,
        baseline.eligibility_status,
    )

    return JobEvaluationResult(
        job_id=baseline.job_id,
        eligibility_status=baseline.eligibility_status,
        eligibility_details=baseline.eligibility_details,
        overall_score=final_score,
        component_scores=components,
        matched_skills=llm_resp.data.matched_skills or baseline.matched_skills,
        missing_skills=llm_resp.data.missing_skills or baseline.missing_skills,
        strengths=llm_resp.data.strengths or baseline.strengths,
        concerns=llm_resp.data.concerns or baseline.concerns,
        recommendation=recommendation,
        recommended_resume_id=baseline.recommended_resume_id,
        recommended_resume_name=baseline.recommended_resume_name,
        explanation=llm_resp.data.explanation,
        evidence={
            **baseline.evidence,
            "raw_weighted_score": raw_score,
            "ineligible_override_applied": baseline.eligibility_status == "INELIGIBLE",
            "prompt_version": llm_resp.prompt_version,
        },
        model_name=llm_resp.model_name,
        evaluation_version=EVALUATION_VERSION,
        used_fallback=False,
    )
