"""Unit tests for the HydraJob FastAPI HTTPX client wrapper."""

from __future__ import annotations

import json

import httpx
import pytest

from services.api_client import (
    DEFAULT_API_BASE_URL,
    HydraJobApiClient,
    build_api_client_from_env,
)


def test_api_client_sends_api_key_header_when_configured() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    with HydraJobApiClient(
        base_url="http://backend:8000/",
        api_key="super-secret-key-123",
        transport=transport,
    ) as client:
        assert client.base_url == "http://backend:8000"
        assert client.has_api_key is True
        result = client.get_health()

    assert result.reachable is True
    assert result.status == "healthy"
    assert captured_headers.get("x-api-key") == "super-secret-key-123"


def test_api_client_omits_api_key_header_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    with build_api_client_from_env(transport=transport) as client:
        assert client.base_url == DEFAULT_API_BASE_URL
        assert client.has_api_key is False
        client.get_health()

    assert "x-api-key" not in captured_headers


def test_build_api_client_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://backend:8000///")
    monkeypatch.setenv("APP_API_KEY", "env-key-value")

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"status": "ok"})

    with build_api_client_from_env(transport=httpx.MockTransport(handler)) as client:
        assert client.base_url == "http://backend:8000"
        assert client.has_api_key is True
        client.get_health()

    assert len(captured) == 1
    assert str(captured[0].url) == "http://backend:8000/health"
    assert captured[0].headers["x-api-key"] == "env-key-value"


def test_get_readiness_handles_200_and_503() -> None:
    def ready_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ready", "database": "ok"})

    with HydraJobApiClient(transport=httpx.MockTransport(ready_handler)) as client:
        ok_res = client.get_readiness()
    assert ok_res.reachable is True
    assert ok_res.ready is True
    assert ok_res.status == "healthy"
    assert ok_res.database_status == "healthy"

    def not_ready_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"status": "not_ready", "database": {"status": "unavailable", "detail": "DB down"}},
        )

    with HydraJobApiClient(transport=httpx.MockTransport(not_ready_handler)) as client:
        fail_res = client.get_readiness()
    assert fail_res.reachable is True
    assert fail_res.ready is False
    assert fail_res.status == "unavailable"
    assert fail_res.database_status == "unavailable"
    assert fail_res.status_code == 503
    assert "not ready" in (fail_res.error or "").lower()


def test_get_system_status_parses_nested_services_payload() -> None:
    payload = {
        "status": "ok",
        "environment": "development",
        "services": {
            "fastapi": {"status": "ok"},
            "postgres": {"status": "ok", "detail": "SELECT 1 succeeded"},
            "ollama": {"status": "degraded", "detail": "Model not pulled", "model": "qwen2.5:7b"},
        },
        "ollama_model": "qwen2.5:7b",
        "timestamp_utc": "2026-11-14T10:30:00Z",
        "timestamp_ist": "2026-11-14T16:00:00+05:30",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with HydraJobApiClient(transport=httpx.MockTransport(handler)) as client:
        status = client.get_system_status()

    assert status.reachable is True
    assert status.overall_status == "healthy"
    assert status.environment == "development"
    assert status.fastapi.status == "healthy"
    assert status.postgres.status == "healthy"
    assert status.postgres.detail == "SELECT 1 succeeded"
    assert status.ollama.status == "degraded"
    assert status.ollama_model == "qwen2.5:7b"
    assert status.server_time_utc == "2026-11-14T10:30:00Z"
    assert status.server_time_ist == "2026-11-14T16:00:00+05:30"


def test_get_system_status_parses_alternate_timestamp_and_service_keys() -> None:
    payload = {
        "overall_status": "degraded",
        "app_env": "production",
        "database": "healthy",
        "ollama": {"available": False, "error": "Connection refused"},
        "model": "llama3.1:8b",
        "timestamps": {
            "utc": "2026-11-14T10:00:00+00:00",
            "asia_kolkata": "2026-11-14T15:30:00+05:30",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with HydraJobApiClient(transport=httpx.MockTransport(handler)) as client:
        status = client.get_system_status()

    assert status.overall_status == "degraded"
    assert status.environment == "production"
    assert status.postgres.status == "healthy"
    assert status.ollama.status == "unavailable"
    assert status.ollama.detail == "Connection refused"
    assert status.ollama_model == "llama3.1:8b"
    assert status.server_time_utc == "2026-11-14T10:00:00+00:00"
    assert status.server_time_ist == "2026-11-14T15:30:00+05:30"


def test_friendly_error_when_backend_unreachable() -> None:
    def connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    secret = "do-not-leak-this-secret-token"
    with HydraJobApiClient(
        base_url="http://backend:8000",
        api_key=secret,
        transport=httpx.MockTransport(connect_error_handler),
    ) as client:
        overview = client.fetch_overview()

    assert overview.health.reachable is False
    assert overview.readiness.reachable is False
    assert overview.system_status.reachable is False
    assert "cannot reach fastapi backend" in (overview.health.error or "").lower()
    assert "IST" in overview.checked_at_ist
    assert secret not in (overview.health.error or "")
    assert secret not in (overview.system_status.error or "")


def test_friendly_error_on_timeout() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timed out", request=request)

    with HydraJobApiClient(transport=httpx.MockTransport(timeout_handler)) as client:
        res = client.get_system_status()

    assert res.reachable is False
    assert res.overall_status == "unavailable"
    assert "timed out" in (res.error or "").lower()


def test_friendly_error_on_auth_failure_and_malformed_json() -> None:
    secret = "my-secret-api-key"

    def unauth_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid API key"})

    with HydraJobApiClient(
        api_key=secret,
        transport=httpx.MockTransport(unauth_handler),
    ) as client:
        unauth = client.get_system_status()
        crud_unauth = client.list_jobs()

    assert unauth.reachable is True
    assert unauth.status_code == 401
    assert "authentication failed" in (unauth.error or "").lower()
    assert secret not in (unauth.error or "")
    assert crud_unauth.ok is False
    assert crud_unauth.status_code == 401
    assert secret not in (crud_unauth.error or "")

    def bad_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    with HydraJobApiClient(transport=httpx.MockTransport(bad_json_handler)) as client:
        bad = client.get_health()

    assert bad.reachable is True
    assert bad.status == "unavailable"
    assert "invalid json" in (bad.error or "").lower()


def test_validation_422_error_formatting_and_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/companies":
            return httpx.Response(
                422,
                json={"detail": [{"loc": ["body", "name"], "msg": "Field required"}]},
            )
        raise httpx.ConnectError("refused", request=request)

    with HydraJobApiClient(transport=httpx.MockTransport(handler)) as client:
        err_422 = client.create_company({})
        err_conn = client.list_jobs()

    assert err_422.ok is False
    assert err_422.status_code == 422
    assert "body.name: Field required" in (err_422.error or "")
    assert err_conn.ok is False
    assert "cannot reach fastapi backend" in (err_conn.error or "").lower()


def test_all_crud_discovery_and_email_client_endpoints() -> None:
    calls: list[tuple[str, str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        calls.append((request.method, request.url.path, str(request.url.query), body))

        list_paths = {
            "/api/v1/resumes",
            "/api/v1/companies",
            "/api/v1/sources",
            "/api/v1/jobs",
            "/api/v1/jobs/j1/evaluations",
            "/api/v1/applications",
            "/api/v1/applications/a1/events",
            "/api/v1/tasks",
            "/api/v1/searches",
            "/api/v1/discovery/runs",
            "/api/v1/discovery/failed-sources",
            "/api/v1/emails",
        }
        if request.method == "GET" and request.url.path in list_paths:
            return httpx.Response(
                200,
                json={"items": [{"id": "item-1"}], "total": 1, "limit": 20, "offset": 0},
            )
        return httpx.Response(200, json={"id": "obj-1", "status": "ok"})

    with HydraJobApiClient(api_key="k", transport=httpx.MockTransport(handler)) as client:
        assert client.get_profile().ok
        assert client.update_profile({"name": "Test"}).ok
        assert client.list_resumes().items == [{"id": "item-1"}]
        assert client.create_resume({"name": "ML"}).ok
        assert client.update_resume("r1", {"is_preferred": True}).ok
        assert client.archive_resume("r1").ok

        assert client.list_companies(search="OpenAI").total == 1
        assert client.create_company({"name": "OpenAI"}).ok
        assert client.update_company("c1", {"industry": "AI"}).ok
        assert client.archive_company("c1").ok
        assert client.list_sources(is_active=True).total == 1
        assert client.register_source({"source_name": "Careers"}).ok
        assert client.update_source("s1", {"source_name": "Updated"}).ok
        assert client.test_source("s1").ok
        assert client.scan_source("s1").ok
        assert client.toggle_source_active("s1", False).ok
        assert client.archive_source("s1").ok

        assert client.list_jobs(search="ML", limit=20, offset=0).total == 1
        assert client.get_job("j1").ok
        assert client.create_job({"title": "ML Engineer"}).ok
        assert client.update_job("j1", {"title": "Senior ML"}).ok
        assert client.archive_job("j1").ok
        assert client.ingest_job_url("https://example.com/jobs/1").ok
        assert client.get_ingestion_run("run1").ok
        assert client.reprocess_ingestion_run("run1").ok
        assert client.evaluate_job("j1", resume_id="r1").ok
        assert client.list_job_evaluations("j1").total == 1

        assert client.list_applications(status="APPLIED").total == 1
        assert client.create_application({"job_id": "j1"}).ok
        assert client.update_application_status("a1", "APPLIED", notes="Sent").ok
        assert client.list_application_events("a1").total == 1

        assert client.list_tasks(status="PENDING").total == 1
        assert client.create_task({"title": "Apply"}).ok
        assert client.update_task("t1", {"title": "Apply now"}).ok
        assert client.update_task_status("t1", "COMPLETED").ok
        assert client.archive_task("t1").ok

        assert client.list_searches(is_active=True).total == 1
        assert client.create_search({"name": "ML 2027"}).ok
        assert client.update_search("sr1", {"is_active": False}).ok
        assert client.archive_search("sr1").ok
        assert client.trigger_scan_all().ok
        assert client.trigger_run_search("sr1").ok
        assert client.list_discovery_runs(run_type="URL_INGEST").total == 1
        assert client.list_failed_sources().total == 1

        assert client.list_email_messages(needs_review=True).total == 1
        assert client.ingest_synthetic_email({"subject": "OA Invite"}).ok
        assert client.review_email_message("e1", {"classification": "OA_INVITATION"}).ok

    recorded_routes = {(m, p) for m, p, _, _ in calls}
    assert ("GET", "/api/v1/profile") in recorded_routes
    assert ("POST", "/api/v1/jobs/ingest") in recorded_routes
    assert ("POST", "/api/v1/jobs/j1/evaluate") in recorded_routes
    assert ("POST", "/api/v1/discovery/scan-source/s1") in recorded_routes
    assert ("POST", "/api/v1/discovery/scan-all") in recorded_routes
    assert ("POST", "/api/v1/discovery/run-search/sr1") in recorded_routes
    assert ("POST", "/api/v1/emails/ingest-synthetic") in recorded_routes
    assert ("POST", "/api/v1/emails/e1/review") in recorded_routes
