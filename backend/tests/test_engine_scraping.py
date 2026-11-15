"""Offline tests for LLM client, SSRF, URL utils, extractors, adapters, dedup, and rate limits."""

import asyncio
import json
import socket
import threading
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.llm import PROMPT_VERSION, OllamaClient
from app.services.scraping import (
    ADAPTER_REGISTRY,
    DomainRateLimiter,
    ExistingJobFingerprint,
    SSRFValidationError,
    canonicalize_job_url,
    compute_dedup_decision,
    extract_generic_html,
    extract_job_from_html,
    extract_job_with_ollama,
    extract_json_ld_job,
    extract_opengraph_metadata,
    fetch_with_playwright,
    get_adapter,
    inspect_and_recommend_adapter,
    safe_fetch_url,
    validate_redirect_hop,
    validate_safe_url,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# SSRF & Safe Fetch Tests
# ---------------------------------------------------------------------------


def test_ssrf_blocks_schemes_credentials_and_local_hosts() -> None:
    blocked = [
        "",
        "file:///etc/passwd",
        "ftp://example.com/jobs.json",
        "javascript:alert(1)",
        "https://user:secret@example.com/jobs",
        "https://token@example.com/jobs",
        "http://localhost:8000/health",
        "http://sub.localhost/jobs",
        "http://ollama.local/api/tags",
        "http://service.internal/jobs",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://127.0.0.1:8000/jobs",
        "http://10.0.0.5/jobs",
        "http://172.16.10.2/jobs",
        "http://192.168.1.50/jobs",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/jobs",
        "http://0.1.2.3/jobs",
        "http://224.0.0.1/jobs",
        "http://[::1]:8000/jobs",
        "http://[fc00::1]/jobs",
        "http://[fe80::1]/jobs",
        "http://[::ffff:127.0.0.1]/jobs",
        "http://2130706433/jobs",
    ]
    for bad_url in blocked:
        with pytest.raises(SSRFValidationError):
            validate_safe_url(bad_url, resolve_dns=False)


def test_ssrf_dns_resolution_blocks_private_and_allows_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_private_dns(host: str, port: int, type: int = 0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_private_dns)
    with pytest.raises(SSRFValidationError, match="non-public IP"):
        validate_safe_url("https://rebind.example.com/job/1", resolve_dns=True)

    def fake_public_dns(host: str, port: int, type: int = 0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_public_dns)
    assert (
        validate_safe_url("https://careers.example.com/jobs/1", resolve_dns=True)
        == "https://careers.example.com/jobs/1"
    )


async def test_ssrf_redirect_hop_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_public_dns(host: str, port: int, type: int = 0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_public_dns)

    with pytest.raises(SSRFValidationError):
        validate_redirect_hop(
            "https://careers.example.com/start",
            "http://169.254.169.254/latest/meta-data/",
            resolve_dns=True,
        )

    def redirect_to_loopback(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:8080/internal"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_to_loopback)) as client:
        with pytest.raises(SSRFValidationError):
            await safe_fetch_url("https://careers.example.com/job", client=client, resolve_dns=True)

    def safe_redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"Location": "https://careers.example.com/new"})
        return httpx.Response(200, text="<html><h1>ML Engineer</h1></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(safe_redirect_handler)) as client:
        result = await safe_fetch_url(
            "https://careers.example.com/old",
            client=client,
            resolve_dns=True,
        )
        assert result.final_url == "https://careers.example.com/new"
        assert result.redirect_chain == ["https://careers.example.com/old"]
        assert "ML Engineer" in result.text


# ---------------------------------------------------------------------------
# URL Canonicalization Tests
# ---------------------------------------------------------------------------


def test_canonicalize_job_url_strips_tracking_fragments_and_trailing_slash() -> None:
    raw = (
        "HTTPS://Boards.Greenhouse.IO:443/acme/jobs/12345/"
        "?utm_source=linkedin&utm_medium=social&gh_src=xyz&gh_jid=12345"
        "&ashby_jid=9&ref=top&source=x&fbclid=fb&gclid=gc&dept=ai&id=42#apply-now"
    )
    assert (
        canonicalize_job_url(raw)
        == "https://boards.greenhouse.io/acme/jobs/12345?dept=ai&id=42"
    )
    assert canonicalize_job_url("http://Example.com:80/") == "http://example.com"


# ---------------------------------------------------------------------------
# Multi-layer Extraction & Lazy Playwright Tests
# ---------------------------------------------------------------------------


def test_extractors_json_ld_opengraph_and_generic_html() -> None:
    json_ld_html = _read_fixture("job_json_ld.html")
    job_ld = extract_json_ld_job(json_ld_html, base_url="https://careers.acme-ai.example/jobs")
    assert job_ld is not None
    assert job_ld.company == "Acme AI"
    assert job_ld.title == "Machine Learning Engineer Intern"
    assert job_ld.location == "Bengaluru, Karnataka, India"
    assert job_ld.currency == "INR"
    assert "75000-100000" in (job_ld.salary or "")
    assert job_ld.application_deadline == "2026-12-31"
    assert job_ld.external_job_id == "ACME-ML-2027"
    assert "Python" in job_ld.required_skills
    assert "PyTorch" in job_ld.required_skills

    # Priority order: JSON-LD wins over OG tags present in same file
    merged = extract_job_from_html(json_ld_html, url="https://careers.acme-ai.example/jobs")
    assert merged.company == "Acme AI"
    assert merged.title == "Machine Learning Engineer Intern"

    og_html = _read_fixture("job_opengraph.html")
    og_data = extract_opengraph_metadata(og_html, base_url="https://jobs.vectorlabs.example")
    assert og_data.company == "VectorLabs"
    assert og_data.title == "NLP Research Intern"
    assert "Transformers" in og_data.required_skills
    assert og_data.application_deadline is None

    generic_html = _read_fixture("job_generic.html")
    gen_data = extract_generic_html(generic_html)
    assert gen_data.title == "AI Systems Engineer"
    assert gen_data.company == "NovaQuant"
    assert gen_data.location == "Bengaluru, India"
    assert gen_data.graduation_year_requirement == "2027"
    assert gen_data.application_deadline is None
    assert len(gen_data.responsibilities) == 2
    assert len(gen_data.qualifications) == 2
    assert "TinyML" in gen_data.preferred_skills
    assert "PyTorch" in gen_data.required_skills


async def test_playwright_graceful_unavailability_and_ssrf_guard() -> None:
    with pytest.raises(SSRFValidationError):
        await fetch_with_playwright("http://127.0.0.1:8501", resolve_dns=False)

    res = await fetch_with_playwright("https://93.184.216.34/careers", resolve_dns=False)
    assert res.available is False
    assert res.html is None
    assert res.error is not None


# ---------------------------------------------------------------------------
# OllamaClient & LLM Extraction Tests
# ---------------------------------------------------------------------------


class _SimpleSample(BaseModel):
    answer: str


def test_ollama_client_settings_and_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal.test:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "15")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    client = OllamaClient(sync_transport=httpx.MockTransport(handler))
    assert client.base_url == "http://ollama.internal.test:11434"
    assert client.model == "qwen2.5:7b"
    assert client.timeout == 15.0
    assert client.prompt_version == PROMPT_VERSION == "v1.0"

    health = client.check_health()
    assert health.reachable is True
    assert health.model_available is True

    # Unreachable check never raises
    def down_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    down_client = OllamaClient(sync_transport=httpx.MockTransport(down_handler))
    down_health = down_client.check_health()
    assert down_health.reachable is False


async def test_ollama_client_retries_validation_fallback_and_concurrency() -> None:
    attempts = 0
    active_calls = 0
    max_active_calls = 0

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts, active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        try:
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": "loading model"})
            return httpx.Response(
                200,
                json={"message": {"content": '```json\n{"answer": "ok"}\n```'}},
            )
        finally:
            active_calls -= 1

    client = OllamaClient(
        base_url="http://ollama:11434",
        model="llama3.1:8b",
        max_retries=2,
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(flaky_handler),
    )
    res1, res2 = await asyncio.gather(
        client.agenerate_structured(prompt="hi", response_model=_SimpleSample),
        client.agenerate_structured(prompt="hi2", response_model=_SimpleSample),
    )
    assert res1.data.answer == "ok"
    assert res2.data.answer == "ok"
    assert res1.used_fallback is False
    assert max_active_calls == 1

    # Sync concurrency lock check
    sync_active = 0
    sync_max = 0

    def sync_handler(request: httpx.Request) -> httpx.Response:
        nonlocal sync_active, sync_max
        sync_active += 1
        sync_max = max(sync_max, sync_active)
        try:
            return httpx.Response(200, json={"response": '{"answer": "sync-ok"}'})
        finally:
            sync_active -= 1

    sync_client = OllamaClient(
        model="llama3.1:8b",
        backoff_seconds=0.0,
        sync_transport=httpx.MockTransport(sync_handler),
    )
    assert isinstance(sync_client._sync_lock, type(threading.Lock()))
    sync_resp = sync_client.generate_structured(prompt="hi", response_model=_SimpleSample)
    assert sync_resp.data.answer == "sync-ok"
    assert sync_max == 1


async def test_extract_job_with_ollama_success_and_malformed_fallback() -> None:
    generic_html = _read_fixture("job_generic.html")
    base = extract_job_from_html(generic_html)

    def good_llm(request: httpx.Request) -> httpx.Response:
        payload = {
            "company": "NovaQuant",
            "title": "AI Systems Engineer",
            "location": "Bengaluru, India",
            "country": "India",
            "employment_type": "FULL_TIME",
            "workplace_type": "ONSITE",
            "experience_requirement": "0-1 years",
            "graduation_year_requirement": "2027",
            "degree_requirement": "B.Tech CSE",
            "required_skills": ["C++", "Python", "PyTorch"],
            "preferred_skills": ["TinyML", "ONNX"],
            "responsibilities": [],
            "qualifications": [],
            "salary": None,
            "currency": None,
            "application_deadline": None,
            "application_url": None,
            "description": None,
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(payload)}})

    good_client = OllamaClient(
        model="llama3.1:8b",
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(good_llm),
    )
    extracted, llm_meta = await extract_job_with_ollama(
        base.description or "",
        ollama_client=good_client,
        base_data=base,
    )
    assert llm_meta.used_fallback is False
    assert extracted.degree_requirement == "B.Tech CSE"
    assert extracted.application_deadline is None

    def malformed_llm(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "{not valid json!!!"}})

    bad_client = OllamaClient(
        model="llama3.1:8b",
        max_retries=1,
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(malformed_llm),
    )
    fallback_job, fallback_meta = await extract_job_with_ollama(
        base.description or "",
        ollama_client=bad_client,
        base_data=base,
    )
    assert fallback_meta.used_fallback is True
    assert fallback_job.title == "AI Systems Engineer"
    assert fallback_job.application_deadline is None


# ---------------------------------------------------------------------------
# Source Adapters & Onboarding Inspection Tests
# ---------------------------------------------------------------------------


def test_adapters_registry_parsing_and_inspection() -> None:
    expected = {
        "greenhouse",
        "lever",
        "ashby",
        "generic_json",
        "json_ld",
        "generic_html",
        "browser_rendered",
    }
    assert expected.issubset(set(ADAPTER_REGISTRY))

    gh_json = _read_fixture("greenhouse_jobs.json")
    gh_jobs = get_adapter("greenhouse").parse_listings(
        gh_json, "https://boards.greenhouse.io/acme", company_name="Acme"
    )
    assert len(gh_jobs) == 2
    assert gh_jobs[0].external_id == "4012345"
    assert gh_jobs[0].canonical_url == "https://boards.greenhouse.io/acme/jobs/4012345"
    assert (
        get_adapter("greenhouse").build_listing_url("https://boards.greenhouse.io/acme", page=2)
        == "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true&page=2"
    )

    lever_json = _read_fixture("lever_postings.json")
    lever_jobs = get_adapter("lever").parse_listings(
        lever_json, "https://jobs.lever.co/vectorai", company_name="VectorAI"
    )
    assert len(lever_jobs) == 1
    assert lever_jobs[0].canonical_url == "https://jobs.lever.co/vectorai/lever-uuid-101"

    ashby_json = _read_fixture("ashby_jobs.json")
    ashby_jobs = get_adapter("ashby").parse_listings(
        ashby_json, "https://jobs.ashbyhq.com/synthlabs", company_name="SynthLabs"
    )
    assert len(ashby_jobs) == 1
    assert ashby_jobs[0].canonical_url == "https://jobs.ashbyhq.com/synthlabs/ashby-901"

    gen_json = _read_fixture("generic_jobs.json")
    gen_jobs = get_adapter("generic_json").parse_listings(
        gen_json, "https://careers.visioncore.example/api/jobs"
    )
    assert len(gen_jobs) == 1
    assert gen_jobs[0].canonical_url == "https://careers.visioncore.example/jobs/cv-engineer"

    list_html = _read_fixture("career_list_generic.html")
    html_jobs = get_adapter("generic_html").parse_listings(
        list_html, "https://careers.helios.example/careers", company_name="Helios"
    )
    assert len(html_jobs) == 2
    assert {j.title for j in html_jobs} == {"AI Research Intern", "Computer Vision Engineer"}

    # Inspection recommendations
    gh_insp = inspect_and_recommend_adapter("https://boards.greenhouse.io/acme", gh_json)
    assert gh_insp.detected_ats == "greenhouse"
    assert gh_insp.recommended_adapter == "greenhouse"
    assert gh_insp.status == "READY"
    assert gh_insp.sample_jobs_count == 2

    ld_insp = inspect_and_recommend_adapter(
        "https://careers.acme-ai.example/jobs/ml",
        _read_fixture("job_json_ld.html"),
    )
    assert ld_insp.recommended_adapter == "json_ld"
    assert ld_insp.status == "READY"

    spa_insp = inspect_and_recommend_adapter(
        "https://careers.example.com/openings",
        _read_fixture("career_spa_shell.html"),
    )
    assert spa_insp.recommended_adapter == "browser_rendered"
    assert spa_insp.status == "NEEDS_CONFIGURATION"

    unknown_insp = inspect_and_recommend_adapter("https://careers.example.com/unknown")
    assert unknown_insp.status == "NEEDS_CONFIGURATION"


# ---------------------------------------------------------------------------
# Deduplicator & Rate Limiter Tests
# ---------------------------------------------------------------------------


def test_deduplicator_matches_correctly_and_prevents_false_merges() -> None:
    existing = [
        ExistingJobFingerprint(
            job_id="job-1",
            canonical_url="https://boards.greenhouse.io/acme/jobs/101",
            source_type="greenhouse",
            external_id="101",
            company="Acme AI Inc.",
            title="Software Engineer",
            location="Bengaluru, India",
            description=(
                "Build distributed Python microservices, FastAPI endpoints, PostgreSQL schemas, "
                "and ML inference pipelines for production search."
            ),
        ),
        ExistingJobFingerprint(
            job_id="job-2",
            canonical_url="https://careers.beta.example/jobs/500",
            source_type="generic_html",
            external_id="500",
            company="Beta Systems",
            title="Software Engineer",
            location="Hyderabad, India",
            description="Develop React frontend dashboards and TypeScript UI components.",
        ),
    ]

    # 1. Canonical URL match (even with tracking params)
    d_url = compute_dedup_decision(
        canonical_url="https://boards.greenhouse.io/acme/jobs/101/?utm_source=x&gh_src=y",
        existing_jobs=existing,
    )
    assert d_url.is_duplicate is True
    assert d_url.matched_job_id == "job-1"
    assert d_url.match_reason == "canonical_url"

    # 2. (source_type, external_id) match
    d_ext = compute_dedup_decision(
        canonical_url="https://acme.example/mirror/101",
        source_type="greenhouse",
        external_id="101",
        existing_jobs=existing,
    )
    assert d_ext.is_duplicate is True
    assert d_ext.matched_job_id == "job-1"
    assert d_ext.match_reason == "source_external_id"

    # 3. Composite match with similar description
    d_comp = compute_dedup_decision(
        canonical_url="https://aggregator.example/acme-swe-blr",
        company="Acme AI",
        title="Software Engineer",
        location="Bangalore, India",
        description=(
            "Build distributed Python microservices, FastAPI endpoints, PostgreSQL schemas, "
            "and machine learning inference pipelines for search."
        ),
        existing_jobs=existing,
    )
    assert d_comp.is_duplicate is True
    assert d_comp.matched_job_id == "job-1"
    assert d_comp.match_reason == "composite_metadata"

    # 4. Identical title at different location must NOT merge
    d_diff_loc = compute_dedup_decision(
        company="Acme AI",
        title="Software Engineer",
        location="Pune, India",
        description=existing[0].description,
        existing_jobs=existing,
    )
    assert d_diff_loc.is_duplicate is False

    # 5. Identical title at different company must NOT merge
    d_diff_comp = compute_dedup_decision(
        company="Gamma Corp",
        title="Software Engineer",
        location="Bengaluru, India",
        description=existing[0].description,
        existing_jobs=existing,
    )
    assert d_diff_comp.is_duplicate is False

    # 6. Same company + title + location, completely unrelated description must NOT merge
    d_diff_desc = compute_dedup_decision(
        company="Acme AI",
        title="Software Engineer",
        location="Bengaluru, India",
        description=(
            "Write low-level embedded C firmware for automotive CAN bus microcontrollers "
            "and real-time RTOS safety diagnostics."
        ),
        existing_jobs=existing,
    )
    assert d_diff_desc.is_duplicate is False


async def test_domain_rate_limiter_enforces_cooldown_and_concurrency() -> None:
    now = 100.0
    sleeps: list[float] = []

    def fake_clock() -> float:
        return now

    async def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = DomainRateLimiter(
        default_cooldown_seconds=2.0,
        max_concurrent_per_domain=1,
        max_total_concurrent=2,
        clock=fake_clock,
        async_sleep=fake_sleep,
    )

    async with limiter.acquire("https://acme.example/jobs/1") as domain:
        assert domain == "acme.example"
        assert limiter.active_count("acme.example") == 1

    assert limiter.active_count("acme.example") == 0

    # Immediate second request to same domain triggers 2.0s cooldown
    async with limiter.acquire("https://acme.example/jobs/2"):
        pass
    assert sleeps == [2.0]

    # Different domain does not trigger acme.example's cooldown
    async with limiter.acquire("https://other.example/jobs/1"):
        pass
    assert sleeps == [2.0]
