"""Streamlit AppTest smoke tests verifying all HydraJob dashboard pages."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from services.api_client import HydraJobApiClient

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent


def _full_mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/health/ready":
            return httpx.Response(200, json={"status": "ready", "database": "ok"})
        if path == "/api/v1/system/status":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "environment": "development",
                    "timestamps": {
                        "utc": "2026-11-14T10:30:00Z",
                        "asia_kolkata": "2026-11-14T16:00:00+05:30",
                    },
                    "services": {
                        "api": {"status": "ok"},
                        "database": {"status": "ok"},
                        "ollama": {"status": "ok", "model": "qwen2.5:7b", "model_available": True},
                    },
                },
            )
        if path == "/api/v1/profile":
            return httpx.Response(
                200,
                json={
                    "name": "Student",
                    "email": "student@example.edu",
                    "university": "IIT Jodhpur",
                    "degree": "B.Tech",
                    "branch": "CSE",
                    "graduation_year": 2027,
                    "cgpa": 8.5,
                    "skills": ["Python", "PyTorch", "SQL"],
                    "preferred_roles": ["ML Engineer"],
                    "preferred_locations": ["Bengaluru"],
                    "excluded_locations": [],
                },
            )
        if path == "/api/v1/resumes":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "res-1",
                            "name": "ML Resume v1",
                            "file_type": "pdf",
                            "skills": ["Python", "PyTorch"],
                            "is_preferred": True,
                            "is_active": True,
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                },
            )
        if path == "/api/v1/companies":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "comp-1",
                            "name": "Anthropic",
                            "industry": "AI",
                            "website": "https://www.anthropic.com",
                            "notes": "Target AI lab",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        if path == "/api/v1/sources":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "src-1",
                            "company_id": "comp-1",
                            "source_name": "Anthropic Careers",
                            "career_url": "https://boards.greenhouse.io/anthropic",
                            "adapter_name": "greenhouse",
                            "status": "READY",
                            "is_active": True,
                            "last_successful_scan_at": "2026-11-14T10:00:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        if path == "/api/v1/jobs":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "job-1",
                            "company_id": "comp-1",
                            "title": "ML Engineer Intern",
                            "location": "Bengaluru",
                            "employment_type": "INTERNSHIP",
                            "workplace_type": "HYBRID",
                            "status": "ACTIVE",
                            "required_skills": ["Python", "PyTorch"],
                            "preferred_skills": ["RAG"],
                            "application_deadline": "2026-12-01T18:00:00Z",
                            "first_seen_at": "2026-11-14T09:00:00Z",
                            "last_seen_at": "2026-11-14T10:00:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        if path == "/api/v1/jobs/job-1":
            return httpx.Response(
                200,
                json={
                    "id": "job-1",
                    "company_id": "comp-1",
                    "title": "ML Engineer Intern",
                    "location": "Bengaluru",
                    "status": "ACTIVE",
                    "required_skills": ["Python", "PyTorch"],
                    "preferred_skills": ["RAG"],
                    "description": "Build LLM systems.",
                },
            )
        if path == "/api/v1/jobs/job-1/evaluations":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "eval-1",
                            "eligibility_status": "ELIGIBLE",
                            "overall_score": 88,
                            "component_scores": {
                                "eligibility": 95,
                                "technical": 90,
                                "experience": 85,
                                "role_relevance": 85,
                                "location": 80,
                            },
                            "matched_skills": ["Python", "PyTorch"],
                            "missing_skills": [],
                            "strengths": ["Strong ML match"],
                            "concerns": [],
                            "recommendation": "HIGH_PRIORITY",
                            "explanation": "Matches IITJ 2027 ML profile.",
                            "model_name": "qwen2.5:7b",
                            "evaluation_version": "v1.0",
                            "evaluated_at": "2026-11-14T10:25:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        if path == "/api/v1/applications":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "app-1",
                            "job_id": "job-1",
                            "selected_resume_id": "res-1",
                            "status": "PREPARING",
                            "priority": "HIGH",
                            "match_score": 88,
                            "eligibility_status": "ELIGIBLE",
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                },
            )
        if path == "/api/v1/applications/app-1/events":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "ev-1",
                            "event_type": "STATUS_CHANGE",
                            "previous_status": "DISCOVERED",
                            "new_status": "PREPARING",
                            "source": "manual",
                            "description": "Started preparing application",
                            "occurred_at": "2026-11-14T10:26:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                },
            )
        if path == "/api/v1/tasks":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "task-1",
                            "title": "Review job description",
                            "task_type": "PREPARING",
                            "status": "PENDING",
                            "priority": "HIGH",
                            "due_date": "2026-11-20T12:00:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 30,
                    "offset": 0,
                },
            )
        if path == "/api/v1/searches":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "srch-1",
                            "name": "2027 ML Internships",
                            "keywords": ["ml", "llm"],
                            "roles": ["ML Engineer"],
                            "locations": ["Bengaluru"],
                            "min_match_score": 70,
                            "is_active": True,
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        if path == "/api/v1/discovery/runs":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "run-1",
                            "run_type": "URL_INGEST",
                            "status": "COMPLETED",
                            "url": "https://example.com/job/1",
                            "extracted_job_id": "job-1",
                            "jobs_new": 1,
                            "started_at": "2026-11-14T10:15:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 10,
                    "offset": 0,
                },
            )
        if path == "/api/v1/discovery/failed-sources":
            return httpx.Response(
                200,
                json={"items": [], "total": 0, "limit": 10, "offset": 0},
            )
        if path == "/api/v1/emails":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "mail-1",
                            "sender": "recruiting@anthropic.com",
                            "subject": "OA Invitation",
                            "snippet": "Complete online assessment.",
                            "classification": "OA_INVITATION",
                            "confidence": 0.82,
                            "needs_review": True,
                            "received_at": "2026-11-14T10:20:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "relative_script",
    [
        "app.py",
        "pages/01_Jobs.py",
        "pages/02_Submit_Job_URL.py",
        "pages/03_Companies.py",
        "pages/04_Career_Sources.py",
        "pages/05_Profile_and_Resumes.py",
        "pages/06_Applications.py",
        "pages/07_Tasks.py",
        "pages/08_Search_Configuration.py",
        "pages/09_Recruitment_Emails.py",
        "pages/10_System_Health.py",
    ],
)
def test_all_pages_render_without_exception(
    monkeypatch: pytest.MonkeyPatch,
    relative_script: str,
) -> None:
    transport = _full_mock_transport()

    def client_factory(*args, **kwargs) -> HydraJobApiClient:
        return HydraJobApiClient(
            base_url="http://backend:8000",
            api_key="test-key",
            transport=transport,
        )

    monkeypatch.setattr("services.api_client.build_api_client_from_env", client_factory)
    monkeypatch.setattr("components.system_view.build_api_client_from_env", client_factory)

    at = AppTest.from_file(str(DASHBOARD_ROOT / relative_script), default_timeout=15).run()
    assert not at.exception, f"{relative_script} raised exception: {at.exception}"


def test_system_health_page_renders_when_backend_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    def failing_factory(*args, **kwargs) -> HydraJobApiClient:
        return HydraJobApiClient(
            base_url="http://backend:8000",
            transport=httpx.MockTransport(failing_handler),
        )

    monkeypatch.setattr("services.api_client.build_api_client_from_env", failing_factory)
    monkeypatch.setattr("components.system_view.build_api_client_from_env", failing_factory)

    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages" / "10_System_Health.py")).run()
    assert not at.exception
    markdown_text = "\n".join(m.value for m in at.markdown)
    assert "fastapi backend unreachable" in markdown_text.lower()
    assert "cannot reach fastapi backend" in markdown_text.lower()


def test_recruitment_emails_synthetic_submit_includes_gmail_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_posts: list[dict] = []
    base_transport = _full_mock_transport()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/emails/ingest-synthetic":
            payload = json.loads(request.content.decode("utf-8"))
            captured_posts.append(payload)
            return httpx.Response(201, json={"id": "mail-new", **payload})
        return base_transport.handle_request(request)

    def client_factory(*args, **kwargs) -> HydraJobApiClient:
        return HydraJobApiClient(
            base_url="http://backend:8000",
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("services.api_client.build_api_client_from_env", client_factory)
    monkeypatch.setattr("components.system_view.build_api_client_from_env", client_factory)

    at = AppTest.from_file(
        str(DASHBOARD_ROOT / "pages" / "09_Recruitment_Emails.py"),
        default_timeout=15,
    ).run()
    assert not at.exception
    submit_btn = next(
        b for b in at.button if b.label == "Classify & Ingest Synthetic Email"
    )
    submit_btn.click().run()
    assert not at.exception
    assert len(captured_posts) == 1
    assert captured_posts[0]["gmail_message_id"].startswith("synthetic-")
