"""HTTPX client wrapper for communicating exclusively with the HydraJob FastAPI backend."""

from __future__ import annotations

import os
from typing import Any, Self

import httpx
from pydantic import BaseModel, Field

from services.time_utils import now_kolkata_formatted

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0

_HEALTHY_VALUES = {"ok", "healthy", "ready", "up", "available", "connected", "online"}
_DEGRADED_VALUES = {"degraded", "partial", "warning"}
_UNAVAILABLE_VALUES = {
    "unavailable",
    "unhealthy",
    "down",
    "error",
    "failed",
    "not_ready",
    "unreachable",
    "disconnected",
    "offline",
}


def normalize_status(raw_status: Any) -> str:
    """Map arbitrary backend status values into canonical UI states."""
    if isinstance(raw_status, bool):
        return "healthy" if raw_status else "unavailable"
    if raw_status is None:
        return "unknown"

    text = str(raw_status).strip().lower()
    if text in _HEALTHY_VALUES:
        return "healthy"
    if text in _DEGRADED_VALUES:
        return "degraded"
    if text in _UNAVAILABLE_VALUES:
        return "unavailable"
    return "unknown"


def _extract_service_entry(
    payload: dict[str, Any],
    candidate_keys: tuple[str, ...],
) -> tuple[str, str | None, str | None]:
    """Extract normalized (status, detail, model) from nested or flat status payloads."""
    services = payload.get("services")
    containers: list[dict[str, Any]] = []
    if isinstance(services, dict):
        containers.append(services)
    checks = payload.get("checks")
    if isinstance(checks, dict):
        containers.append(checks)
    containers.append(payload)

    for container in containers:
        for key in candidate_keys:
            if key not in container:
                continue
            entry = container[key]
            if isinstance(entry, dict):
                raw_status = (
                    entry.get("status")
                    if "status" in entry
                    else entry.get("available", entry.get("ok", entry.get("healthy")))
                )
                detail = entry.get("detail") or entry.get("message") or entry.get("error")
                model = entry.get("model") or entry.get("configured_model")
                return (
                    normalize_status(raw_status),
                    str(detail) if detail is not None else None,
                    str(model) if model is not None else None,
                )
            return normalize_status(entry), None, None

    return "unknown", None, None


def _extract_timestamps(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract UTC and Asia/Kolkata timestamps from common backend response shapes."""
    timestamps = payload.get("timestamps")
    if isinstance(timestamps, dict):
        utc_val = timestamps.get("utc") or timestamps.get("timestamp_utc")
        ist_val = (
            timestamps.get("asia_kolkata")
            or timestamps.get("ist")
            or timestamps.get("timestamp_ist")
        )
        if utc_val or ist_val:
            return (
                str(utc_val) if utc_val is not None else None,
                str(ist_val) if ist_val is not None else None,
            )

    utc_val = (
        payload.get("timestamp_utc")
        or payload.get("utc_timestamp")
        or payload.get("utc_time")
        or payload.get("timestamp")
    )
    ist_val = (
        payload.get("timestamp_ist")
        or payload.get("timestamp_kolkata")
        or payload.get("asia_kolkata_time")
        or payload.get("ist_timestamp")
        or payload.get("ist_time")
    )
    return (
        str(utc_val) if utc_val is not None else None,
        str(ist_val) if ist_val is not None else None,
    )


def _format_error_detail(payload: Any, status_code: int) -> str:
    """Extract a readable, secret-safe error message from a FastAPI error body."""
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if isinstance(detail, list):
            parts: list[str] = []
            for item in detail[:4]:
                if isinstance(item, dict):
                    loc = ".".join(str(x) for x in item.get("loc", []))
                    msg = item.get("msg", "validation error")
                    parts.append(f"{loc}: {msg}" if loc else str(msg))
                else:
                    parts.append(str(item))
            if parts:
                return "; ".join(parts)
        if detail is not None:
            return str(detail)
    return f"HTTP {status_code}"


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop None and empty-string query parameters cleanly."""
    if not params:
        return None
    cleaned: dict[str, Any] = {}
    for key, val in params.items():
        if val is None:
            continue
        if isinstance(val, str) and val == "":
            continue
        cleaned[key] = val
    return cleaned or None


class ServiceStatusInfo(BaseModel):
    """Normalized health details for an individual HydraJob subsystem."""

    name: str
    status: str = "unknown"
    detail: str | None = None
    model: str | None = None


class HealthCheckResult(BaseModel):
    """Result from ``GET /health``."""

    reachable: bool
    status: str = "unknown"
    status_code: int | None = None
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ReadinessCheckResult(BaseModel):
    """Result from ``GET /health/ready``."""

    reachable: bool
    ready: bool
    status: str = "unknown"
    database_status: str = "unknown"
    status_code: int | None = None
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SystemStatusResult(BaseModel):
    """Result from ``GET /api/v1/system/status``."""

    reachable: bool
    overall_status: str = "unknown"
    environment: str | None = None
    fastapi: ServiceStatusInfo = Field(default_factory=lambda: ServiceStatusInfo(name="FastAPI"))
    postgres: ServiceStatusInfo = Field(default_factory=lambda: ServiceStatusInfo(name="PostgreSQL"))
    ollama: ServiceStatusInfo = Field(default_factory=lambda: ServiceStatusInfo(name="Ollama"))
    ollama_model: str | None = None
    server_time_utc: str | None = None
    server_time_ist: str | None = None
    status_code: int | None = None
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SystemOverview(BaseModel):
    """Aggregated Phase 0 status fetched from the backend API."""

    api_base_url: str
    checked_at_ist: str
    health: HealthCheckResult
    readiness: ReadinessCheckResult
    system_status: SystemStatusResult


class ApiResponse(BaseModel):
    """Unified typed envelope returned by HydraJob REST CRUD and action methods."""

    ok: bool
    status_code: int | None = None
    data: Any = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    error: str | None = None


class HydraJobApiClient:
    """Thin, secret-safe HTTPX wrapper for the HydraJob FastAPI backend."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        raw_base_url = (base_url or os.getenv("API_BASE_URL") or DEFAULT_API_BASE_URL).strip()
        self.base_url = raw_base_url.rstrip("/") or DEFAULT_API_BASE_URL
        self._api_key = (api_key if api_key is not None else os.getenv("APP_API_KEY", "")).strip()

        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        client_kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "headers": headers,
            "timeout": httpx.Timeout(timeout),
        }
        if transport is not None:
            client_kwargs["transport"] = transport

        self._client = httpx.Client(**client_kwargs)

    @property
    def has_api_key(self) -> bool:
        """Return whether an X-API-Key credential is configured (never exposing its value)."""
        return bool(self._api_key)

    def close(self) -> None:
        """Close the underlying HTTPX client."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _safe_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response | None, str | None]:
        """Execute an HTTP request and translate transport failures into friendly messages."""
        try:
            response = self._client.request(
                method,
                path,
                params=_clean_params(params),
                json=json_body,
            )
            return response, None
        except httpx.TimeoutException:
            return (
                None,
                f"Timed out waiting for FastAPI backend at {self.base_url}{path}.",
            )
        except httpx.ConnectError:
            return (
                None,
                (
                    f"Cannot reach FastAPI backend at {self.base_url}. "
                    "Verify the backend service is running."
                ),
            )
        except httpx.RequestError as exc:
            return (
                None,
                f"Network error contacting FastAPI backend ({type(exc).__name__}).",
            )

    @staticmethod
    def _parse_json_dict(response: httpx.Response) -> tuple[dict[str, Any], str | None]:
        """Decode a JSON object safely without crashing on non-JSON responses."""
        try:
            data = response.json()
        except ValueError:
            return {}, f"Backend returned invalid JSON (HTTP {response.status_code})."
        if not isinstance(data, dict):
            return (
                {},
                f"Backend returned unexpected JSON payload type (HTTP {response.status_code}).",
            )
        return data, None

    def _request_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expect_list: bool = False,
    ) -> ApiResponse:
        """Call a FastAPI JSON endpoint and normalize data, pagination, and errors."""
        response, transport_err = self._safe_request(
            method, path, params=params, json_body=json_body
        )
        if response is None:
            return ApiResponse(ok=False, error=transport_err)

        if response.status_code in (401, 403):
            return ApiResponse(
                ok=False,
                status_code=response.status_code,
                error=(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Verify APP_API_KEY matches the backend X-API-Key configuration."
                ),
            )

        if response.status_code == 204:
            return ApiResponse(ok=True, status_code=204, data={})

        try:
            payload = response.json()
        except ValueError:
            return ApiResponse(
                ok=False,
                status_code=response.status_code,
                error=f"Backend returned invalid JSON (HTTP {response.status_code}).",
            )

        if response.status_code >= 400:
            detail = _format_error_detail(payload, response.status_code)
            return ApiResponse(
                ok=False,
                status_code=response.status_code,
                data=payload,
                error=f"Request failed (HTTP {response.status_code}): {detail}",
            )

        if expect_list:
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                items = [item for item in payload["items"] if isinstance(item, dict)]
                return ApiResponse(
                    ok=True,
                    status_code=response.status_code,
                    data=payload,
                    items=items,
                    total=int(payload.get("total", len(items))),
                    limit=int(payload.get("limit", len(items) or 50)),
                    offset=int(payload.get("offset", 0)),
                )
            if isinstance(payload, list):
                items = [item for item in payload if isinstance(item, dict)]
                return ApiResponse(
                    ok=True,
                    status_code=response.status_code,
                    data=payload,
                    items=items,
                    total=len(items),
                    limit=len(items) or 50,
                    offset=0,
                )

        return ApiResponse(ok=True, status_code=response.status_code, data=payload)

    # ------------------------------------------------------------------
    # Phase 0 Health & System Status
    # ------------------------------------------------------------------

    def get_health(self) -> HealthCheckResult:
        """Call ``GET /health`` to check whether FastAPI is alive."""
        response, transport_err = self._safe_request("GET", "/health")
        if response is None:
            return HealthCheckResult(reachable=False, status="unavailable", error=transport_err)

        payload, parse_err = self._parse_json_dict(response)
        if parse_err:
            return HealthCheckResult(
                reachable=True,
                status="unavailable" if response.status_code >= 500 else "degraded",
                status_code=response.status_code,
                error=parse_err,
            )

        if response.status_code >= 400:
            detail = payload.get("detail") or payload.get("message") or f"HTTP {response.status_code}"
            return HealthCheckResult(
                reachable=True,
                status="unavailable",
                status_code=response.status_code,
                error=f"Health endpoint returned HTTP {response.status_code}: {detail}",
                raw=payload,
            )

        return HealthCheckResult(
            reachable=True,
            status=normalize_status(payload.get("status", "ok")),
            status_code=response.status_code,
            raw=payload,
        )

    def get_readiness(self) -> ReadinessCheckResult:
        """Call ``GET /health/ready`` to check FastAPI + PostgreSQL readiness."""
        response, transport_err = self._safe_request("GET", "/health/ready")
        if response is None:
            return ReadinessCheckResult(
                reachable=False,
                ready=False,
                status="unavailable",
                database_status="unknown",
                error=transport_err,
            )

        payload, parse_err = self._parse_json_dict(response)
        if parse_err:
            return ReadinessCheckResult(
                reachable=True,
                ready=False,
                status="unavailable",
                database_status="unavailable",
                status_code=response.status_code,
                error=parse_err,
            )

        db_status, db_detail, _ = _extract_service_entry(
            payload, ("postgres", "postgresql", "database", "db")
        )
        if response.status_code == 200:
            overall = normalize_status(payload.get("status", "ready"))
            if db_status == "unknown":
                db_status = "healthy" if overall == "healthy" else overall
            return ReadinessCheckResult(
                reachable=True,
                ready=True,
                status=overall,
                database_status=db_status,
                status_code=response.status_code,
                raw=payload,
            )

        detail = (
            db_detail
            or payload.get("detail")
            or payload.get("message")
            or f"HTTP {response.status_code}"
        )
        if db_status == "unknown":
            db_status = "unavailable"
        return ReadinessCheckResult(
            reachable=True,
            ready=False,
            status="unavailable",
            database_status=db_status,
            status_code=response.status_code,
            error=f"Backend is not ready ({detail}).",
            raw=payload,
        )

    def get_system_status(self) -> SystemStatusResult:
        """Call ``GET /api/v1/system/status`` to fetch subsystem availability and timestamps."""
        response, transport_err = self._safe_request("GET", "/api/v1/system/status")
        if response is None:
            return SystemStatusResult(
                reachable=False,
                overall_status="unavailable",
                fastapi=ServiceStatusInfo(name="FastAPI", status="unavailable", detail=transport_err),
                postgres=ServiceStatusInfo(name="PostgreSQL", status="unknown"),
                ollama=ServiceStatusInfo(name="Ollama", status="unknown"),
                error=transport_err,
            )

        if response.status_code in (401, 403):
            return SystemStatusResult(
                reachable=True,
                overall_status="degraded",
                fastapi=ServiceStatusInfo(
                    name="FastAPI",
                    status="healthy",
                    detail="Backend is reachable, but API authentication failed.",
                ),
                postgres=ServiceStatusInfo(name="PostgreSQL", status="unknown"),
                ollama=ServiceStatusInfo(name="Ollama", status="unknown"),
                status_code=response.status_code,
                error=(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Verify APP_API_KEY matches the backend X-API-Key configuration."
                ),
            )

        payload, parse_err = self._parse_json_dict(response)
        if parse_err:
            return SystemStatusResult(
                reachable=True,
                overall_status="unavailable",
                fastapi=ServiceStatusInfo(name="FastAPI", status="degraded", detail=parse_err),
                status_code=response.status_code,
                error=parse_err,
            )

        if response.status_code >= 500:
            detail = payload.get("detail") or payload.get("message") or f"HTTP {response.status_code}"
            return SystemStatusResult(
                reachable=True,
                overall_status="unavailable",
                fastapi=ServiceStatusInfo(name="FastAPI", status="degraded", detail=str(detail)),
                status_code=response.status_code,
                error=f"System status endpoint failed (HTTP {response.status_code}): {detail}",
                raw=payload,
            )

        api_status, api_detail, _ = _extract_service_entry(
            payload, ("fastapi", "api", "backend", "app")
        )
        if api_status == "unknown":
            api_status = "healthy"

        pg_status, pg_detail, _ = _extract_service_entry(
            payload, ("postgres", "postgresql", "database", "db")
        )
        ollama_status, ollama_detail, nested_model = _extract_service_entry(
            payload, ("ollama", "llm")
        )

        ollama_model = payload.get("ollama_model") or payload.get("model") or nested_model
        overall_raw = payload.get("status") or payload.get("overall_status")
        overall_status = normalize_status(overall_raw)
        if overall_status == "unknown":
            statuses = [api_status, pg_status, ollama_status]
            if all(s == "healthy" for s in statuses):
                overall_status = "healthy"
            elif "unavailable" in statuses or "degraded" in statuses:
                overall_status = "degraded"

        utc_ts, ist_ts = _extract_timestamps(payload)
        env_name = payload.get("environment") or payload.get("app_env")

        return SystemStatusResult(
            reachable=True,
            overall_status=overall_status,
            environment=str(env_name) if env_name is not None else None,
            fastapi=ServiceStatusInfo(name="FastAPI", status=api_status, detail=api_detail),
            postgres=ServiceStatusInfo(name="PostgreSQL", status=pg_status, detail=pg_detail),
            ollama=ServiceStatusInfo(
                name="Ollama",
                status=ollama_status,
                detail=ollama_detail,
                model=str(ollama_model) if ollama_model is not None else None,
            ),
            ollama_model=str(ollama_model) if ollama_model is not None else None,
            server_time_utc=utc_ts,
            server_time_ist=ist_ts,
            status_code=response.status_code,
            raw=payload,
        )

    def fetch_overview(self) -> SystemOverview:
        """Collect all Phase 0 health and system status endpoints in one pass."""
        health = self.get_health()
        readiness = self.get_readiness()
        system_status = self.get_system_status()
        return SystemOverview(
            api_base_url=self.base_url,
            checked_at_ist=now_kolkata_formatted(),
            health=health,
            readiness=readiness,
            system_status=system_status,
        )

    # ------------------------------------------------------------------
    # Profile & Resumes
    # ------------------------------------------------------------------

    def get_profile(self) -> ApiResponse:
        """Fetch the configurable user profile via ``GET /api/v1/profile``."""
        return self._request_api("GET", "/api/v1/profile")

    def update_profile(self, payload: dict[str, Any]) -> ApiResponse:
        """Update the user profile via ``PUT /api/v1/profile``."""
        return self._request_api("PUT", "/api/v1/profile", json_body=payload)

    def list_resumes(
        self,
        *,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List stored resume versions via ``GET /api/v1/resumes``."""
        return self._request_api(
            "GET",
            "/api/v1/resumes",
            params={"include_archived": include_archived, "limit": limit, "offset": offset},
            expect_list=True,
        )

    def create_resume(self, payload: dict[str, Any]) -> ApiResponse:
        """Create a resume record via ``POST /api/v1/resumes``."""
        return self._request_api("POST", "/api/v1/resumes", json_body=payload)

    def update_resume(self, resume_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update an existing resume record via ``PUT /api/v1/resumes/{id}``."""
        return self._request_api("PUT", f"/api/v1/resumes/{resume_id}", json_body=payload)

    def archive_resume(self, resume_id: str) -> ApiResponse:
        """Soft-archive a resume record via ``DELETE /api/v1/resumes/{id}``."""
        return self._request_api("DELETE", f"/api/v1/resumes/{resume_id}")

    # ------------------------------------------------------------------
    # Companies & Career Sources
    # ------------------------------------------------------------------

    def list_companies(
        self,
        *,
        search: str | None = None,
        industry: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List companies via ``GET /api/v1/companies``."""
        return self._request_api(
            "GET",
            "/api/v1/companies",
            params={
                "search": search,
                "industry": industry,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def create_company(self, payload: dict[str, Any]) -> ApiResponse:
        """Create a company record via ``POST /api/v1/companies``."""
        return self._request_api("POST", "/api/v1/companies", json_body=payload)

    def update_company(self, company_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update a company record via ``PUT /api/v1/companies/{id}``."""
        return self._request_api("PUT", f"/api/v1/companies/{company_id}", json_body=payload)

    def archive_company(self, company_id: str) -> ApiResponse:
        """Soft-archive a company record via ``DELETE /api/v1/companies/{id}``."""
        return self._request_api("DELETE", f"/api/v1/companies/{company_id}")

    def list_sources(
        self,
        *,
        company_id: str | None = None,
        is_active: bool | None = None,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List career-page sources via ``GET /api/v1/sources``."""
        return self._request_api(
            "GET",
            "/api/v1/sources",
            params={
                "company_id": company_id,
                "is_active": is_active,
                "status": status,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def register_source(self, payload: dict[str, Any]) -> ApiResponse:
        """Register a career-page source via ``POST /api/v1/sources``."""
        return self._request_api("POST", "/api/v1/sources", json_body=payload)

    def update_source(self, source_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update a career-page source via ``PUT /api/v1/sources/{id}``."""
        return self._request_api("PUT", f"/api/v1/sources/{source_id}", json_body=payload)

    def test_source(self, source_id: str) -> ApiResponse:
        """Run adapter detection and test extraction via ``POST /api/v1/sources/{id}/test``."""
        return self._request_api("POST", f"/api/v1/sources/{source_id}/test")

    def scan_source(self, source_id: str) -> ApiResponse:
        """Trigger a discovery scan for one source via ``POST /api/v1/discovery/scan-source/{id}``."""
        return self._request_api("POST", f"/api/v1/discovery/scan-source/{source_id}")

    def toggle_source_active(self, source_id: str, is_active: bool) -> ApiResponse:
        """Enable or disable active monitoring for a source via ``PUT /api/v1/sources/{id}``."""
        return self._request_api(
            "PUT",
            f"/api/v1/sources/{source_id}",
            json_body={"is_active": is_active},
        )

    def archive_source(self, source_id: str) -> ApiResponse:
        """Soft-archive a career-page source via ``DELETE /api/v1/sources/{id}``."""
        return self._request_api("DELETE", f"/api/v1/sources/{source_id}")

    # ------------------------------------------------------------------
    # Jobs, Ingestion & Evaluation
    # ------------------------------------------------------------------

    def list_jobs(
        self,
        *,
        search: str | None = None,
        company_id: str | None = None,
        status: str | None = None,
        employment_type: str | None = None,
        workplace_type: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List jobs with pagination and filters via ``GET /api/v1/jobs``."""
        return self._request_api(
            "GET",
            "/api/v1/jobs",
            params={
                "search": search,
                "company_id": company_id,
                "status": status,
                "employment_type": employment_type,
                "workplace_type": workplace_type,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def get_job(self, job_id: str) -> ApiResponse:
        """Fetch a single job detail record via ``GET /api/v1/jobs/{id}``."""
        return self._request_api("GET", f"/api/v1/jobs/{job_id}")

    def create_job(self, payload: dict[str, Any]) -> ApiResponse:
        """Create a job manually via ``POST /api/v1/jobs``."""
        return self._request_api("POST", "/api/v1/jobs", json_body=payload)

    def update_job(self, job_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update job fields via ``PUT /api/v1/jobs/{id}``."""
        return self._request_api("PUT", f"/api/v1/jobs/{job_id}", json_body=payload)

    def archive_job(self, job_id: str) -> ApiResponse:
        """Soft-archive a job via ``DELETE /api/v1/jobs/{id}``."""
        return self._request_api("DELETE", f"/api/v1/jobs/{job_id}")

    def ingest_job_url(self, url: str, *, use_ollama: bool = True) -> ApiResponse:
        """Submit a job URL for safe ingestion via ``POST /api/v1/jobs/ingest``."""
        return self._request_api(
            "POST",
            "/api/v1/jobs/ingest",
            json_body={"url": url, "use_ollama": use_ollama},
        )

    def get_ingestion_run(self, run_id: str) -> ApiResponse:
        """Fetch ingestion run status via ``GET /api/v1/discovery/runs/{id}``."""
        return self._request_api("GET", f"/api/v1/discovery/runs/{run_id}")

    def reprocess_ingestion_run(self, run_id: str) -> ApiResponse:
        """Retry/reprocess an ingestion run via ``POST /api/v1/discovery/runs/{id}/retry``."""
        return self._request_api("POST", f"/api/v1/discovery/runs/{run_id}/retry")

    def evaluate_job(self, job_id: str, *, resume_id: str | None = None) -> ApiResponse:
        """Run eligibility and match scoring via ``POST /api/v1/jobs/{id}/evaluate``."""
        body: dict[str, Any] | None = {"resume_id": resume_id} if resume_id else None
        return self._request_api("POST", f"/api/v1/jobs/{job_id}/evaluate", json_body=body)

    def list_job_evaluations(self, job_id: str) -> ApiResponse:
        """List historical evaluations for a job via ``GET /api/v1/jobs/{id}/evaluations``."""
        return self._request_api(
            "GET",
            f"/api/v1/jobs/{job_id}/evaluations",
            expect_list=True,
        )

    # ------------------------------------------------------------------
    # Applications & Events
    # ------------------------------------------------------------------

    def list_applications(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List applications via ``GET /api/v1/applications``."""
        return self._request_api(
            "GET",
            "/api/v1/applications",
            params={
                "status": status,
                "priority": priority,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def create_application(self, payload: dict[str, Any]) -> ApiResponse:
        """Create an application for an existing job via ``POST /api/v1/applications``."""
        return self._request_api("POST", "/api/v1/applications", json_body=payload)

    def update_application(self, application_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update application metadata via ``PUT /api/v1/applications/{id}``."""
        return self._request_api("PUT", f"/api/v1/applications/{application_id}", json_body=payload)

    def update_application_status(
        self,
        application_id: str,
        status: str,
        *,
        notes: str | None = None,
    ) -> ApiResponse:
        """Transition an application status via ``PATCH /api/v1/applications/{id}/status``."""
        body: dict[str, Any] = {"status": status}
        if notes is not None:
            body["notes"] = notes
        return self._request_api(
            "PATCH",
            f"/api/v1/applications/{application_id}/status",
            json_body=body,
        )

    def list_application_events(self, application_id: str) -> ApiResponse:
        """Fetch immutable event history via ``GET /api/v1/applications/{id}/events``."""
        return self._request_api(
            "GET",
            f"/api/v1/applications/{application_id}/events",
            expect_list=True,
        )

    # ------------------------------------------------------------------
    # Internal Tasks
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        *,
        status: str | None = None,
        task_type: str | None = None,
        job_id: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List internal tasks via ``GET /api/v1/tasks``."""
        return self._request_api(
            "GET",
            "/api/v1/tasks",
            params={
                "status": status,
                "task_type": task_type,
                "job_id": job_id,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def create_task(self, payload: dict[str, Any]) -> ApiResponse:
        """Create an internal task via ``POST /api/v1/tasks``."""
        return self._request_api("POST", "/api/v1/tasks", json_body=payload)

    def update_task(self, task_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update task fields via ``PUT /api/v1/tasks/{id}``."""
        return self._request_api("PUT", f"/api/v1/tasks/{task_id}", json_body=payload)

    def update_task_status(self, task_id: str, status: str) -> ApiResponse:
        """Update task status via ``PATCH /api/v1/tasks/{id}/status``."""
        return self._request_api(
            "PATCH",
            f"/api/v1/tasks/{task_id}/status",
            json_body={"status": status},
        )

    def archive_task(self, task_id: str) -> ApiResponse:
        """Soft-archive a task via ``DELETE /api/v1/tasks/{id}``."""
        return self._request_api("DELETE", f"/api/v1/tasks/{task_id}")

    # ------------------------------------------------------------------
    # Searches & Discovery Runs
    # ------------------------------------------------------------------

    def list_searches(
        self,
        *,
        is_active: bool | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List saved search configurations via ``GET /api/v1/searches``."""
        return self._request_api(
            "GET",
            "/api/v1/searches",
            params={
                "is_active": is_active,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def create_search(self, payload: dict[str, Any]) -> ApiResponse:
        """Create a search configuration via ``POST /api/v1/searches``."""
        return self._request_api("POST", "/api/v1/searches", json_body=payload)

    def update_search(self, search_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Update a search configuration via ``PUT /api/v1/searches/{id}``."""
        return self._request_api("PUT", f"/api/v1/searches/{search_id}", json_body=payload)

    def archive_search(self, search_id: str) -> ApiResponse:
        """Soft-archive a search configuration via ``DELETE /api/v1/searches/{id}``."""
        return self._request_api("DELETE", f"/api/v1/searches/{search_id}")

    def trigger_scan_all(self) -> ApiResponse:
        """Trigger scans for all active sources via ``POST /api/v1/discovery/scan-all``."""
        return self._request_api("POST", "/api/v1/discovery/scan-all")

    def trigger_run_search(self, search_id: str) -> ApiResponse:
        """Execute a saved search via ``POST /api/v1/discovery/run-search/{id}``."""
        return self._request_api("POST", f"/api/v1/discovery/run-search/{search_id}")

    def list_discovery_runs(
        self,
        *,
        run_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List discovery and ingestion runs via ``GET /api/v1/discovery/runs``."""
        return self._request_api(
            "GET",
            "/api/v1/discovery/runs",
            params={
                "run_type": run_type,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def list_failed_sources(self, *, limit: int = 50, offset: int = 0) -> ApiResponse:
        """List sources with recent scan failures via ``GET /api/v1/discovery/failed-sources``."""
        return self._request_api(
            "GET",
            "/api/v1/discovery/failed-sources",
            params={"limit": limit, "offset": offset},
            expect_list=True,
        )

    # ------------------------------------------------------------------
    # Recruitment Emails (Phase 8)
    # ------------------------------------------------------------------

    def list_email_messages(
        self,
        *,
        needs_review: bool | None = None,
        classification: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        """List classified recruitment emails via ``GET /api/v1/emails``."""
        return self._request_api(
            "GET",
            "/api/v1/emails",
            params={
                "needs_review": needs_review,
                "classification": classification,
                "limit": limit,
                "offset": offset,
            },
            expect_list=True,
        )

    def ingest_synthetic_email(self, payload: dict[str, Any]) -> ApiResponse:
        """Ingest a synthetic recruitment email via ``POST /api/v1/emails/ingest-synthetic``."""
        return self._request_api("POST", "/api/v1/emails/ingest-synthetic", json_body=payload)

    def review_email_message(self, email_id: str, payload: dict[str, Any]) -> ApiResponse:
        """Confirm or correct an email match/classification via ``POST /api/v1/emails/{id}/review``."""
        return self._request_api("POST", f"/api/v1/emails/{email_id}/review", json_body=payload)


def build_api_client_from_env(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transport: httpx.BaseTransport | None = None,
) -> HydraJobApiClient:
    """Create a configured ``HydraJobApiClient`` from environment variables."""
    return HydraJobApiClient(
        base_url=os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL),
        api_key=os.getenv("APP_API_KEY", ""),
        timeout=timeout,
        transport=transport,
    )
