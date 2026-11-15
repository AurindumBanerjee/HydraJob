"""Offline engine tests for eligibility evaluation, weighted scoring, and task policy."""

import json

import httpx

from app.services.llm import OllamaClient
from app.services.matching import (
    ComponentScores,
    JobRequirementsSnapshot,
    ProfileSnapshot,
    ResumeSnapshot,
    TaskPolicyThresholds,
    aevaluate_job,
    classify_score_band,
    compute_weighted_score,
    evaluate_eligibility,
    evaluate_job,
    generate_application_tasks,
    recommend_best_resume,
)


def _sample_profile() -> ProfileSnapshot:
    return ProfileSnapshot(
        name="Aarav Candidate",
        degree="B.Tech",
        branch="Computer Science and Engineering",
        university="IIT Jodhpur",
        graduation_year=2027,
        cgpa=8.6,
        cgpa_scale=10.0,
        experience_years=0.5,
        experience_summary="Data Science Intern at InfoEdge building NLP and ML pipelines.",
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
        ],
        projects=[
            "Script-Identifier",
            "TinyML",
            "ANN in C",
            "Smart Surveillance",
            "Company-knowledge model research",
        ],
        preferred_roles=["ML Engineer", "AI Engineer", "Data Scientist", "ML / AI Intern"],
        preferred_locations=["Bengaluru", "Hyderabad", "Pune", "Remote"],
        excluded_locations=["Chennai"],
        work_authorizations=["India"],
        requires_sponsorship=True,
    )


def _sample_resumes() -> list[ResumeSnapshot]:
    return [
        ResumeSnapshot(
            id=1,
            name="Systems_C_Embedded_Resume.pdf",
            skills=["C", "C++", "TinyML", "Embedded Systems"],
            extracted_text="ANN in C, TinyML microcontroller inference, low-level systems.",
            is_preferred=True,
            is_active=True,
        ),
        ResumeSnapshot(
            id=2,
            name="AI_ML_NLP_Resume.pdf",
            skills=["Python", "PyTorch", "NLP", "LLMs", "RAG", "SQL"],
            extracted_text=(
                "InfoEdge Data Science Intern, company-knowledge model research, "
                "RAG pipelines and LLM fine-tuning."
            ),
            is_preferred=False,
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Eligibility Tests
# ---------------------------------------------------------------------------


def test_eligibility_eligible_and_all_failure_modes() -> None:
    profile = _sample_profile()

    eligible_job = JobRequirementsSnapshot(
        job_id=10,
        title="ML / AI Intern",
        company="Acme AI",
        location="Bengaluru, India",
        graduation_year_requirement=2027,
        degree_requirement="B.Tech in Computer Science and Engineering",
        min_cgpa=7.5,
        experience_requirement="0-1 years",
        work_authorization_requirement="Work authorization in India",
        required_skills=["Python", "PyTorch", "LLMs", "RAG"],
    )
    elig = evaluate_eligibility(profile, eligible_job)
    assert elig.status == "ELIGIBLE"
    assert elig.failed_conditions == []

    # 1. Graduation year mismatch
    grad_fail = eligible_job.model_copy(update={"graduation_year_requirement": 2025})
    assert evaluate_eligibility(profile, grad_fail).status == "INELIGIBLE"
    assert "graduation_year" in evaluate_eligibility(profile, grad_fail).failed_conditions

    # 2. Experience mismatch
    exp_fail = eligible_job.model_copy(update={"experience_requirement": "3+ years experience"})
    res_exp = evaluate_eligibility(profile, exp_fail)
    assert res_exp.status == "INELIGIBLE"
    assert "experience_years" in res_exp.failed_conditions

    # 3. Degree mismatch (PhD required)
    deg_fail = eligible_job.model_copy(
        update={"degree_requirement": "PhD in Machine Learning required"}
    )
    res_deg = evaluate_eligibility(profile, deg_fail)
    assert res_deg.status == "INELIGIBLE"
    assert "degree_branch" in res_deg.failed_conditions

    # 4. CGPA below minimum
    cgpa_fail = eligible_job.model_copy(update={"min_cgpa": 9.2})
    res_cgpa = evaluate_eligibility(profile, cgpa_fail)
    assert res_cgpa.status == "INELIGIBLE"
    assert "min_cgpa" in res_cgpa.failed_conditions

    # 5. Excluded location
    loc_fail = eligible_job.model_copy(update={"location": "Chennai, India"})
    res_loc = evaluate_eligibility(profile, loc_fail)
    assert res_loc.status == "INELIGIBLE"
    assert "location" in res_loc.failed_conditions

    # 6. Work authorization / sponsorship failure
    auth_fail = eligible_job.model_copy(
        update={
            "work_authorization_requirement": "Must be a US Citizen without sponsorship",
            "sponsorship_available": False,
        }
    )
    res_auth = evaluate_eligibility(profile, auth_fail)
    assert res_auth.status == "INELIGIBLE"
    assert "work_authorization" in res_auth.failed_conditions


def test_missing_requirements_never_produce_false_certainty() -> None:
    profile = _sample_profile()

    # Zero eligibility criteria -> NOT_EVALUATED (never ELIGIBLE)
    empty_job = JobRequirementsSnapshot(
        job_id=20,
        title="Software Developer",
        description="Build awesome backend services with Python.",
    )
    res_empty = evaluate_eligibility(profile, empty_job)
    assert res_empty.status == "NOT_EVALUATED"

    # Only location specified -> core academic/experience missing -> UNCERTAIN
    loc_only_job = JobRequirementsSnapshot(
        job_id=21,
        title="AI Engineer",
        location="Bengaluru, India",
    )
    res_loc_only = evaluate_eligibility(profile, loc_only_job)
    assert res_loc_only.status == "UNCERTAIN"

    # Job requires CGPA, candidate profile missing CGPA -> UNCERTAIN
    profile_no_cgpa = profile.model_copy(update={"cgpa": None})
    cgpa_job = JobRequirementsSnapshot(
        job_id=22,
        title="ML Intern",
        graduation_year_requirement=2027,
        degree_requirement="B.Tech CSE",
        min_cgpa=8.0,
        experience_requirement="0-1 years",
        location="Remote",
    )
    res_missing_cgpa = evaluate_eligibility(profile_no_cgpa, cgpa_job)
    assert res_missing_cgpa.status == "UNCERTAIN"
    assert "min_cgpa" in res_missing_cgpa.uncertain_conditions


# ---------------------------------------------------------------------------
# Weighted Scoring & Resume Recommendation Tests
# ---------------------------------------------------------------------------


def test_weighted_formula_resume_selection_and_ineligible_override() -> None:
    components = ComponentScores(
        eligibility=90,
        technical=85,
        experience=80,
        role_relevance=90,
        location=70,
    )
    # 0.30*90 + 0.30*85 + 0.20*80 + 0.10*90 + 0.10*70 = 84.5 -> round() = 84
    expected_score = round(0.30 * 90 + 0.30 * 85 + 0.20 * 80 + 0.10 * 90 + 0.10 * 70)
    assert compute_weighted_score(components) == expected_score

    profile = _sample_profile()
    resumes = _sample_resumes()

    ml_job = JobRequirementsSnapshot(
        job_id=30,
        title="ML / AI Intern",
        company="Acme AI",
        location="Bengaluru, India",
        graduation_year_requirement=2027,
        degree_requirement="B.Tech CSE",
        min_cgpa=8.0,
        experience_requirement="0-1 years",
        required_skills=["Python", "PyTorch", "LLMs", "RAG", "NLP"],
        preferred_skills=["SQL"],
        description="Build RAG and LLM fine-tuning pipelines in PyTorch.",
    )
    best_resume, _ = recommend_best_resume(ml_job, resumes, profile)
    assert best_resume is not None
    assert best_resume.id == 2  # AI_ML_NLP_Resume beats preferred Systems resume on overlap

    eval_ok = evaluate_job(profile=profile, job=ml_job, resumes=resumes)
    assert eval_ok.eligibility_status == "ELIGIBLE"
    assert eval_ok.overall_score >= 85
    assert eval_ok.recommendation == "HIGH_PRIORITY"
    assert eval_ok.recommended_resume_id == 2
    assert "Python" in eval_ok.matched_skills
    assert eval_ok.missing_skills == []
    assert eval_ok.evaluation_version == "v1.0"

    # Mandatory INELIGIBLE must override high skill/role/location alignment!
    ineligible_high_skill_job = ml_job.model_copy(
        update={
            "job_id": 31,
            "experience_requirement": "5+ years of production ML experience",
        }
    )
    eval_bad = evaluate_job(profile=profile, job=ineligible_high_skill_job, resumes=resumes)
    assert eval_bad.eligibility_status == "INELIGIBLE"
    assert eval_bad.component_scores.eligibility == 0
    assert eval_bad.component_scores.technical >= 80
    assert eval_bad.recommendation == "INELIGIBLE"
    assert eval_bad.overall_score < 55
    assert eval_bad.evidence["ineligible_override_applied"] is True


async def test_aevaluate_job_with_ollama_and_malformed_fallback() -> None:
    profile = _sample_profile()
    resumes = _sample_resumes()
    job = JobRequirementsSnapshot(
        job_id=40,
        title="ML Engineer Intern",
        location="Remote",
        graduation_year_requirement=2027,
        degree_requirement="B.Tech CSE",
        experience_requirement="0-1 years",
        required_skills=["Python", "PyTorch", "Docker"],
    )

    def ok_handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "technical_score": 88,
            "experience_score": 82,
            "role_relevance_score": 92,
            "location_score": 100,
            "matched_skills": ["Python", "PyTorch"],
            "missing_skills": ["Docker"],
            "strengths": ["Strong ML/LLM projects"],
            "concerns": ["Docker not explicitly listed"],
            "explanation": "Strong technical and academic alignment.",
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(payload)}})

    ok_client = OllamaClient(
        model="llama3.1:8b",
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(ok_handler),
    )
    llm_eval = await aevaluate_job(
        profile=profile,
        job=job,
        resumes=resumes,
        ollama_client=ok_client,
        use_ollama=True,
    )
    assert llm_eval.used_fallback is False
    assert llm_eval.model_name == "llama3.1:8b"
    assert llm_eval.missing_skills == ["Docker"]
    assert llm_eval.overall_score >= 85

    def broken_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "NOT_JSON"}})

    bad_client = OllamaClient(
        model="llama3.1:8b",
        max_retries=1,
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(broken_handler),
    )
    fb_eval = await aevaluate_job(
        profile=profile,
        job=job,
        resumes=resumes,
        ollama_client=bad_client,
        use_ollama=True,
    )
    assert fb_eval.used_fallback is True
    assert fb_eval.eligibility_status == "ELIGIBLE"


# ---------------------------------------------------------------------------
# Task Policy & Idempotency Tests
# ---------------------------------------------------------------------------


def test_task_policy_thresholds_and_idempotency() -> None:
    assert classify_score_band(85, "ELIGIBLE").band == "EXCELLENT"
    assert classify_score_band(84, "ELIGIBLE").band == "GOOD"
    assert classify_score_band(70, "ELIGIBLE").band == "GOOD"
    assert classify_score_band(69, "ELIGIBLE").band == "REVIEW"
    assert classify_score_band(55, "ELIGIBLE").band == "REVIEW"
    assert classify_score_band(54, "ELIGIBLE").band == "LOW_RELEVANCE"
    assert classify_score_band(95, "INELIGIBLE").qualifies_for_tasks is False

    profile = _sample_profile()
    resumes = _sample_resumes()
    high_job = JobRequirementsSnapshot(
        job_id=50,
        title="ML / AI Intern",
        company="Acme AI",
        location="Bengaluru, India",
        graduation_year_requirement=2027,
        degree_requirement="B.Tech CSE",
        experience_requirement="0-1 years",
        required_skills=["Python", "PyTorch", "LLMs", "RAG"],
    )
    ev_high = evaluate_job(profile=profile, job=high_job, resumes=resumes)
    tasks = generate_application_tasks(
        ev_high,
        job_title=high_job.title,
        company_name="Acme AI",
    )
    assert [t.title for t in tasks] == [
        "Review job description",
        "Select resume",
        "Prepare application",
        "Submit application",
    ]
    assert all(t.priority == "HIGH" for t in tasks)

    # Re-running with existing keys/titles produces zero duplicate tasks
    duplicate_run = generate_application_tasks(
        ev_high,
        job_title=high_job.title,
        company_name="Acme AI",
        existing_task_keys=[t.idempotency_key for t in tasks],
    )
    assert duplicate_run == []

    # Review band (55-69) generates only Review job description
    ev_review = ev_high.model_copy(update={"overall_score": 62, "recommendation": "REVIEW"})
    review_tasks = generate_application_tasks(ev_review, job_title="Analyst", company_name="Co")
    assert [t.title for t in review_tasks] == ["Review job description"]

    # Low relevance (<55) generates no tasks
    ev_low = ev_high.model_copy(update={"overall_score": 48, "recommendation": "LOW_RELEVANCE"})
    assert generate_application_tasks(ev_low) == []

    # Ineligible never generates tasks even if score were artificially high
    ev_inelig = ev_high.model_copy(
        update={"eligibility_status": "INELIGIBLE", "overall_score": 90}
    )
    assert generate_application_tasks(ev_inelig) == []

    # Uncertain defaults to no auto tasks unless configured
    ev_uncertain = ev_high.model_copy(
        update={"eligibility_status": "UNCERTAIN", "overall_score": 82}
    )
    assert generate_application_tasks(ev_uncertain) == []
    assert (
        len(
            generate_application_tasks(
                ev_uncertain,
                thresholds=TaskPolicyThresholds(allow_uncertain_eligibility=True),
            )
        )
        == 4
    )
