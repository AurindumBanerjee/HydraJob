"""End-to-end API integration tests for Phases 2-8 using offline fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.services.scraping.ssrf import SafeFetchResult

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_job_url_ingest_ssrf_dedup_and_reprocess(client: TestClient) -> None:
    for unsafe_url in (
        "http://127.0.0.1:8000/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/admin",
    ):
        res = client.post("/api/v1/jobs/ingest", json={"url": unsafe_url})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "ssrf_blocked"

    html_fixture = (FIXTURES_DIR / "job_json_ld.html").read_text(encoding="utf-8")

    ingest_1 = client.post(
        "/api/v1/jobs/ingest",
        json={
            "url": "https://careers.example.com/jobs/ml-intern-2027?utm_source=linkedin",
            "html_content": html_fixture,
            "use_ollama": False,
        },
    )
    assert ingest_1.status_code == 200
    run1 = ingest_1.json()
    assert run1["status"] == "COMPLETED"
    assert run1["jobs_new"] == 1
    assert run1["jobs_updated"] == 0
    assert run1["extracted_job_id"] is not None
    assert run1["canonical_url"] == "https://careers.example.com/jobs/ml-intern-2027"

    run_fetch = client.get(f"/api/v1/jobs/ingest/{run1['id']}")
    assert run_fetch.status_code == 200
    assert run_fetch.json()["extracted_job_id"] == run1["extracted_job_id"]

    # Duplicate canonical URL (trailing slash + tracking param) updates instead of creating one
    ingest_2 = client.post(
        "/api/v1/jobs/ingest",
        json={
            "url": "https://careers.example.com/jobs/ml-intern-2027/?gclid=abc123",
            "html_content": html_fixture,
            "use_ollama": False,
        },
    )
    assert ingest_2.status_code == 200
    run2 = ingest_2.json()
    assert run2["status"] == "COMPLETED"
    assert run2["jobs_new"] == 0
    assert run2["jobs_updated"] == 1
    assert run2["extracted_job_id"] == run1["extracted_job_id"]

    # Reprocess respects max_retries (default 3)
    for expected_retry in (1, 2, 3):
        reproc = client.post(
            f"/api/v1/jobs/ingest/{run1['id']}/reprocess",
            json={
                "url": "https://careers.example.com/jobs/ml-intern-2027",
                "html_content": html_fixture,
                "use_ollama": False,
            },
        )
        assert reproc.status_code == 200
        assert reproc.json()["retry_count"] == expected_retry

    over_limit = client.post(
        f"/api/v1/jobs/ingest/{run1['id']}/reprocess",
        json={
            "url": "https://careers.example.com/jobs/ml-intern-2027",
            "html_content": html_fixture,
            "use_ollama": False,
        },
    )
    assert over_limit.status_code == 409
    assert over_limit.json()["error"]["code"] == "max_retries_exceeded"


def test_job_evaluation_idempotent_tasks_and_ineligibility_override(
    client: TestClient,
) -> None:
    # Seed profile (IIT Jodhpur B.Tech CSE 2027) and update excluded location
    client.put("/api/v1/profile", json={"excluded_locations": ["Antarctica"]})
    resume = client.post(
        "/api/v1/resumes",
        json={
            "name": "ML & RAG Resume",
            "skills": ["Python", "PyTorch", "NLP", "LLMs", "RAG", "SQL"],
            "is_preferred": True,
        },
    ).json()

    company = client.post("/api/v1/companies", json={"name": "Anthropic India"}).json()

    eligible_job = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company["id"],
            "title": "Machine Learning Engineer Intern",
            "description": "Build LLM and RAG pipelines in Python and PyTorch. Batch of 2027.",
            "location": "Bengaluru",
            "graduation_year_requirement": 2027,
            "degree_requirement": "B.Tech Computer Science",
            "required_skills": ["Python", "PyTorch", "NLP", "LLMs", "RAG"],
        },
    ).json()

    eval1 = client.post(f"/api/v1/jobs/{eligible_job['id']}/evaluate")
    assert eval1.status_code == 200
    ev_body = eval1.json()
    assert ev_body["eligibility_status"] == "ELIGIBLE"
    assert ev_body["overall_score"] >= 70
    assert ev_body["recommended_resume_id"] == resume["id"]

    tasks_first = client.get(f"/api/v1/tasks?job_id={eligible_job['id']}").json()
    assert tasks_first["total"] >= 1

    # Re-evaluating must NOT create duplicate tasks
    eval2 = client.post(
        f"/api/v1/jobs/{eligible_job['id']}/evaluate",
        json={"resume_id": resume["id"]},
    )
    assert eval2.status_code == 200
    tasks_second = client.get(f"/api/v1/tasks?job_id={eligible_job['id']}").json()
    assert tasks_second["total"] == tasks_first["total"]

    history = client.get(f"/api/v1/jobs/{eligible_job['id']}/evaluations").json()
    assert history["total"] == 2

    # Mandatory ineligibility overrides high skill match
    ineligible_job = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company["id"],
            "title": "ML Engineer (2024 Batch Only)",
            "description": "Python, PyTorch, LLMs, RAG expert needed.",
            "location": "Bengaluru",
            "graduation_year_requirement": 2024,
            "required_skills": ["Python", "PyTorch", "LLMs", "RAG"],
        },
    ).json()

    inelig_eval = client.post(f"/api/v1/jobs/{ineligible_job['id']}/evaluate")
    assert inelig_eval.status_code == 200
    assert inelig_eval.json()["eligibility_status"] == "INELIGIBLE"
    assert inelig_eval.json()["recommendation"] == "INELIGIBLE"
    assert client.get(f"/api/v1/tasks?job_id={ineligible_job['id']}").json()["total"] == 0


def test_source_onboarding_scan_closure_rule_failure_isolation_and_search(
    client: TestClient,
) -> None:
    gh_json = (FIXTURES_DIR / "greenhouse_jobs.json").read_text(encoding="utf-8")
    empty_gh_json = '{"jobs": []}'

    reg_res = client.post(
        "/api/v1/sources/register",
        json={
            "company_name": "Example Greenhouse Co",
            "career_url": "https://boards.greenhouse.io/exampleco",
            "sample_content": gh_json,
        },
    )
    assert reg_res.status_code == 201
    source = reg_res.json()
    assert source["adapter_name"] == "greenhouse"
    assert source["status"] == "READY"
    assert source["is_active"] is True

    test_res = client.post(
        f"/api/v1/sources/{source['id']}/test",
        json={"sample_content": gh_json},
    )
    assert test_res.status_code == 200
    assert test_res.json()["detected_ats"] == "greenhouse"
    assert len(test_res.json()["sample_jobs"]) >= 1

    # Scan source with fixture -> discovers jobs
    scan1 = client.post(
        f"/api/v1/discovery/scan-source/{source['id']}",
        json={"sample_content": gh_json},
    )
    assert scan1.status_code == 200
    assert scan1.json()["total_discovered"] >= 1
    assert scan1.json()["total_new"] >= 1

    source_jobs = client.get(f"/api/v1/sources/{source['id']}/jobs").json()
    assert source_jobs["total"] >= 1
    first_job_id = source_jobs["items"][0]["id"]

    # 3-miss rule: missing in 1st & 2nd empty successful scans keeps job ACTIVE; 3rd marks CLOSED
    for miss_num in (1, 2):
        miss_scan = client.post(
            f"/api/v1/discovery/scan-source/{source['id']}",
            json={"sample_content": empty_gh_json},
        )
        assert miss_scan.status_code == 200
        job_state = client.get(f"/api/v1/jobs/{first_job_id}").json()
        assert job_state["missing_scan_count"] == miss_num
        assert job_state["status"] == "ACTIVE"

    miss_scan_3 = client.post(
        f"/api/v1/discovery/scan-source/{source['id']}",
        json={"sample_content": empty_gh_json},
    )
    assert miss_scan_3.status_code == 200
    closed_state = client.get(f"/api/v1/jobs/{first_job_id}").json()
    assert closed_state["missing_scan_count"] == 3
    assert closed_state["status"] == "CLOSED"
    assert closed_state["is_active"] is False

    # Re-activate a fresh scan to test scan-all failure isolation + search execution
    client.post(
        f"/api/v1/discovery/scan-source/{source['id']}",
        json={"sample_content": gh_json},
    )
    generic_html = (FIXTURES_DIR / "career_list_generic.html").read_text(encoding="utf-8")
    failing_src = client.post(
        "/api/v1/sources/register",
        json={
            "company_name": "Flaky Careers Co",
            "career_url": "https://careers.flaky.example.com/jobs",
            "sample_content": generic_html,
        },
    ).json()

    async def fake_safe_fetch(url: str, **_kwargs) -> SafeFetchResult:
        if "flaky.example.com" in url:
            raise RuntimeError("Upstream 503 timeout")
        return SafeFetchResult(
            url=url,
            final_url=url,
            status_code=200,
            headers={"content-type": "application/json"},
            text=gh_json,
        )

    with patch(
        "app.db.repositories.workflows.safe_fetch_url",
        new=AsyncMock(side_effect=fake_safe_fetch),
    ):
        scan_all = client.post("/api/v1/discovery/scan-all")

    assert scan_all.status_code == 200
    runs = scan_all.json()["runs"]
    assert len(runs) == 2
    statuses = {r["source_id"]: r["status"] for r in runs}
    assert statuses[source["id"]] == "COMPLETED"
    assert statuses[failing_src["id"]] == "FAILED"

    failed_list = client.get("/api/v1/discovery/failed-sources").json()
    assert failed_list["total"] == 1
    assert failed_list["items"][0]["id"] == failing_src["id"]

    # Search run over active jobs
    search = client.post(
        "/api/v1/searches",
        json={"name": "Python ML Search", "keywords": ["python"]},
    ).json()
    search_run = client.post(f"/api/v1/discovery/run-search/{search['id']}")
    assert search_run.status_code == 200
    assert search_run.json()["runs"][0]["run_type"] == "SEARCH_RUN"
    assert search_run.json()["runs"][0]["status"] == "COMPLETED"


def test_email_intelligence_confidence_ambiguity_and_regression(client: TestClient) -> None:
    co = client.post(
        "/api/v1/companies",
        json={"name": "NVIDIA", "website": "https://nvidia.com"},
    ).json()
    j1 = client.post(
        "/api/v1/jobs",
        json={"company_id": co["id"], "title": "ML Engineer Intern"},
    ).json()
    j2 = client.post(
        "/api/v1/jobs",
        json={"company_id": co["id"], "title": "CUDA Systems Intern"},
    ).json()

    app1 = client.post(
        "/api/v1/applications",
        json={"job_id": j1["id"], "status": "APPLIED", "thread_id": "thread-nv-ml"},
    ).json()
    app2 = client.post(
        "/api/v1/applications",
        json={"job_id": j2["id"], "status": "OFFER_RECEIVED", "thread_id": "thread-nv-cuda"},
    ).json()

    # 1. High-confidence OA invitation matched unambiguously via thread_id -> auto status update
    oa_res = client.post(
        "/api/v1/emails/ingest-synthetic",
        json={
            "gmail_message_id": "msg-oa-001",
            "thread_id": "thread-nv-ml",
            "sender": "recruiting@nvidia.com",
            "subject": "NVIDIA ML Engineer Intern - HackerRank Online Assessment Invitation",
            "snippet": "Please complete your online assessment within 72 hours.",
        },
    )
    assert oa_res.status_code == 200
    oa_body = oa_res.json()
    assert oa_body["classification"] == "OA_INVITATION"
    assert oa_body["status_applied"] is True
    assert oa_body["needs_review"] is False
    assert oa_body["matched_application_id"] == app1["id"]
    assert client.get(f"/api/v1/applications/{app1['id']}").json()["status"] == "OA_RECEIVED"

    # 2. Duplicate gmail_message_id is idempotent
    dup_res = client.post(
        "/api/v1/emails/ingest-synthetic",
        json={
            "gmail_message_id": "msg-oa-001",
            "thread_id": "thread-nv-ml",
            "sender": "recruiting@nvidia.com",
            "subject": "NVIDIA ML Engineer Intern - HackerRank Online Assessment Invitation",
        },
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["id"] == oa_body["id"]

    # 3. Ambiguous email without thread_id or distinct title -> needs_review=True, no auto update
    ambig_res = client.post(
        "/api/v1/emails/ingest-synthetic",
        json={
            "gmail_message_id": "msg-ambig-002",
            "sender": "careers@nvidia.com",
            "subject": "Interview invitation from NVIDIA recruiting team",
            "snippet": "We would like to schedule an interview for your NVIDIA application.",
        },
    )
    assert ambig_res.status_code == 200
    ambig_body = ambig_res.json()
    assert ambig_body["needs_review"] is True
    assert ambig_body["status_applied"] is False

    review_queue = client.get("/api/v1/emails?needs_review=true").json()
    assert review_queue["total"] == 1
    assert review_queue["items"][0]["id"] == ambig_body["id"]

    # 4. Status regression prevention: OFFER_RECEIVED must NOT regress to ACKNOWLEDGED
    reg_res = client.post(
        "/api/v1/emails/ingest-synthetic",
        json={
            "gmail_message_id": "msg-reg-003",
            "thread_id": "thread-nv-cuda",
            "sender": "recruiting@nvidia.com",
            "subject": "Thank you for applying to NVIDIA",
            "snippet": "We acknowledge receipt of your application.",
        },
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["status_applied"] is False
    assert client.get(f"/api/v1/applications/{app2['id']}").json()["status"] == "OFFER_RECEIVED"

    # 5. Manual review links ambiguous email to app1 and moves OA_RECEIVED -> INTERVIEW_SCHEDULED
    manual_rev = client.post(
        f"/api/v1/emails/{ambig_body['id']}/review",
        json={
            "classification": "INTERVIEW_INVITATION",
            "matched_application_id": app1["id"],
            "apply_status_update": True,
            "needs_review": False,
            "review_notes": "Confirmed for ML Engineer Intern",
        },
    )
    assert manual_rev.status_code == 200
    assert manual_rev.json()["status_applied"] is True
    assert (
        client.get(f"/api/v1/applications/{app1['id']}").json()["status"]
        == "INTERVIEW_SCHEDULED"
    )

    events = client.get(f"/api/v1/applications/{app1['id']}/events").json()
    assert [e["source"] for e in events["items"]] == [
        "manual",
        "EMAIL",
        "EMAIL_MANUAL_REVIEW",
    ]
