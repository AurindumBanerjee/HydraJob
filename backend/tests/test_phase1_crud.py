"""Integration tests for Phase 1 CRUD APIs, relationships, audit history, and migrations."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings


def test_profile_seed_and_update_and_resumes(client: TestClient) -> None:
    get_res = client.get("/api/v1/profile")
    assert get_res.status_code == 200
    profile = get_res.json()
    assert profile["university"] == "IIT Jodhpur"
    assert profile["graduation_year"] == 2027
    assert "InfoEdge" in profile["experience_summary"]
    assert "PyTorch" in profile["skills"]
    assert "TinyML" in profile["projects"]

    put_res = client.put(
        "/api/v1/profile",
        json={"name": "Aurin Candidate", "cgpa": 8.9, "preferred_locations": ["Bengaluru"]},
    )
    assert put_res.status_code == 200
    assert put_res.json()["name"] == "Aurin Candidate"
    assert put_res.json()["cgpa"] == 8.9
    assert put_res.json()["preferred_locations"] == ["Bengaluru"]

    r1 = client.post(
        "/api/v1/resumes",
        json={
            "name": "ML Engineer Resume v1",
            "file_type": "pdf",
            "skills": ["Python", "PyTorch", "RAG"],
            "is_preferred": True,
        },
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = client.post(
        "/api/v1/resumes",
        json={
            "name": "Quant SWE Resume v2",
            "file_type": "pdf",
            "skills": ["C++", "Algorithms"],
            "is_preferred": True,
        },
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]

    list_res = client.get("/api/v1/resumes")
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["total"] == 2
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[r2_id]["is_preferred"] is True
    assert by_id[r1_id]["is_preferred"] is False

    del_res = client.delete(f"/api/v1/resumes/{r1_id}")
    assert del_res.status_code == 200
    assert del_res.json()["is_archived"] is True

    active_list = client.get("/api/v1/resumes").json()
    assert active_list["total"] == 1
    all_list = client.get("/api/v1/resumes?include_archived=true").json()
    assert all_list["total"] == 2


def test_companies_and_sources_crud_and_duplicates(client: TestClient) -> None:
    c1 = client.post(
        "/api/v1/companies",
        json={"name": "Acme AI", "website": "https://acme.example.com", "industry": "AI"},
    )
    assert c1.status_code == 201
    company_id = c1.json()["id"]

    dup = client.post("/api/v1/companies", json={"name": "  acme   ai "})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_company"

    c2 = client.post(
        "/api/v1/companies",
        json={"name": "Beta Quant", "industry": "Quantitative Finance"},
    )
    assert c2.status_code == 201

    filtered = client.get("/api/v1/companies?search=acme&industry=AI").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == company_id

    s1 = client.post(
        "/api/v1/sources",
        json={
            "company_id": company_id,
            "source_name": "Acme Careers",
            "career_url": "HTTPS://Acme.Example.com/careers/?utm_source=test",
            "adapter_name": "greenhouse",
            "status": "READY",
            "is_active": True,
        },
    )
    assert s1.status_code == 201
    source_id = s1.json()["id"]
    assert s1.json()["canonical_url"] == "https://acme.example.com/careers"

    dup_src = client.post(
        "/api/v1/sources",
        json={
            "company_id": company_id,
            "source_name": "Acme Duplicate",
            "career_url": "https://acme.example.com/careers/",
        },
    )
    assert dup_src.status_code == 409

    upd_src = client.put(f"/api/v1/sources/{source_id}", json={"is_active": False})
    assert upd_src.status_code == 200
    assert upd_src.json()["is_active"] is False

    arch_src = client.delete(f"/api/v1/sources/{source_id}")
    assert arch_src.status_code == 200
    assert client.get(f"/api/v1/sources?company_id={company_id}").json()["total"] == 0

    arch_co = client.delete(f"/api/v1/companies/{company_id}")
    assert arch_co.status_code == 200
    assert client.get("/api/v1/companies").json()["total"] == 1


def test_jobs_crud_pagination_and_duplicate_prevention(client: TestClient) -> None:
    co = client.post("/api/v1/companies", json={"name": "NVIDIA"}).json()
    company_id = co["id"]

    j1 = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company_id,
            "title": "ML Engineer Intern",
            "location": "Bengaluru",
            "employment_type": "Internship",
            "required_skills": ["Python", "PyTorch"],
            "application_url": "https://nvidia.example.com/jobs/101?utm_medium=social",
            "external_job_id": "NV-101",
        },
    )
    assert j1.status_code == 201
    job1_id = j1.json()["id"]
    assert j1.json()["canonical_url"] == "https://nvidia.example.com/jobs/101"

    dup_url = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company_id,
            "title": "Different Title",
            "application_url": "https://nvidia.example.com/jobs/101/",
        },
    )
    assert dup_url.status_code == 409

    dup_composite = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company_id,
            "title": "ml engineer intern",
            "location": "bengaluru",
        },
    )
    assert dup_composite.status_code == 409

    j2 = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company_id,
            "title": "Deep Learning Engineer",
            "location": "Hyderabad",
            "employment_type": "Full-time",
        },
    )
    assert j2.status_code == 201

    page1 = client.get("/api/v1/jobs?limit=1&offset=0").json()
    page2 = client.get("/api/v1/jobs?limit=1&offset=1").json()
    assert page1["total"] == 2
    assert len(page1["items"]) == 1
    assert len(page2["items"]) == 1
    assert page1["items"][0]["id"] != page2["items"][0]["id"]

    filtered = client.get("/api/v1/jobs?search=learning&location=hyderabad").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == j2.json()["id"]

    upd = client.put(f"/api/v1/jobs/{job1_id}", json={"salary": "1.2L/month"})
    assert upd.status_code == 200
    assert upd.json()["salary"] == "1.2L/month"
    assert upd.json()["last_changed_at"] is not None

    arch = client.delete(f"/api/v1/jobs/{job1_id}")
    assert arch.status_code == 200
    assert client.get("/api/v1/jobs").json()["total"] == 1


def test_applications_status_transitions_and_immutable_events(client: TestClient) -> None:
    missing_app = client.post("/api/v1/applications", json={"job_id": str(uuid4())})
    assert missing_app.status_code == 404

    co = client.post("/api/v1/companies", json={"name": "Google"}).json()
    job = client.post(
        "/api/v1/jobs",
        json={"company_id": co["id"], "title": "Software Engineer"},
    ).json()

    created = client.post(
        "/api/v1/applications",
        json={
            "job_id": job["id"],
            "status": "TO_APPLY",
            "priority": "HIGH",
            "match_score": 88,
            "eligibility_status": "ELIGIBLE",
            "notes": "Target SWE role",
        },
    )
    assert created.status_code == 201
    app_id = created.json()["id"]

    dup = client.post("/api/v1/applications", json={"job_id": job["id"]})
    assert dup.status_code == 409

    for next_status in ["APPLIED", "OA_RECEIVED", "INTERVIEW_SCHEDULED", "OFFER_RECEIVED"]:
        patch_res = client.patch(
            f"/api/v1/applications/{app_id}/status",
            json={"status": next_status, "description": f"Moved to {next_status}"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == next_status

    fetched = client.get(f"/api/v1/applications/{app_id}").json()
    assert fetched["application_date"] is not None

    events = client.get(f"/api/v1/applications/{app_id}/events").json()
    assert events["total"] == 5
    assert [e["new_status"] for e in events["items"]] == [
        "TO_APPLY",
        "APPLIED",
        "OA_RECEIVED",
        "INTERVIEW_SCHEDULED",
        "OFFER_RECEIVED",
    ]
    assert events["items"][1]["previous_status"] == "TO_APPLY"

    arch = client.delete(f"/api/v1/applications/{app_id}")
    assert arch.status_code == 200
    events_after_archive = client.get(f"/api/v1/applications/{app_id}/events").json()
    assert events_after_archive["total"] == 6


def test_tasks_and_searches_crud_and_api_key_protection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    co = client.post("/api/v1/companies", json={"name": "Atlassian"}).json()
    job = client.post(
        "/api/v1/jobs",
        json={"company_id": co["id"], "title": "Backend Intern"},
    ).json()
    app_rec = client.post(
        "/api/v1/applications",
        json={"job_id": job["id"], "status": "PREPARING"},
    ).json()

    t1 = client.post(
        "/api/v1/tasks",
        json={
            "title": "Tailor resume for Atlassian",
            "job_id": job["id"],
            "application_id": app_rec["id"],
            "task_type": "RESUME_SELECTION",
            "priority": "HIGH",
        },
    )
    assert t1.status_code == 201
    task_id = t1.json()["id"]

    patch_t = client.patch(f"/api/v1/tasks/{task_id}/status", json={"status": "COMPLETED"})
    assert patch_t.status_code == 200
    assert patch_t.json()["status"] == "COMPLETED"

    del_t = client.delete(f"/api/v1/tasks/{task_id}")
    assert del_t.status_code == 200
    assert client.get("/api/v1/tasks").json()["total"] == 0

    s1 = client.post(
        "/api/v1/searches",
        json={
            "name": "India ML Internships 2027",
            "keywords": ["machine learning", "nlp"],
            "locations": ["Bengaluru", "Hyderabad"],
            "graduation_year": 2027,
            "min_match_score": 70,
        },
    )
    assert s1.status_code == 201
    search_id = s1.json()["id"]

    upd_s = client.put(f"/api/v1/searches/{search_id}", json={"is_active": False})
    assert upd_s.status_code == 200
    assert upd_s.json()["is_active"] is False

    del_s = client.delete(f"/api/v1/searches/{search_id}")
    assert del_s.status_code == 200
    assert client.get("/api/v1/searches").json()["total"] == 0

    monkeypatch.setenv("APP_API_KEY", "phase1-test-key")
    get_settings.cache_clear()
    assert client.get("/api/v1/jobs").status_code == 401
    assert (
        client.get("/api/v1/jobs", headers={"X-API-Key": "phase1-test-key"}).status_code == 200
    )


def test_alembic_phase1_to_8_migration_creates_all_tables(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    db_path = tmp_path / "alembic_phase1.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    assert script.get_current_head() == "20261114_0002"

    command.upgrade(alembic_cfg, "head")
    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    expected = {
        "alembic_version",
        "user_profiles",
        "resumes",
        "companies",
        "company_sources",
        "jobs",
        "job_source_references",
        "job_evaluations",
        "job_applications",
        "application_events",
        "tasks",
        "job_searches",
        "ingestion_runs",
        "email_messages",
    }
    assert expected.issubset(tables)

    command.downgrade(alembic_cfg, "base")
    engine = create_engine(db_url)
    try:
        remaining = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert "jobs" not in remaining
    assert "user_profiles" not in remaining
