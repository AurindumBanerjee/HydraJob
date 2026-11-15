"""Tests for X-API-Key authentication and JSON exception handlers."""

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db, get_http_client
from app.core.config import get_settings


def _mock_dependencies(app) -> None:
    mock_db = MagicMock()
    mock_db.execute.return_value = 1
    app.dependency_overrides[get_db] = lambda: (yield mock_db)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": []})
    )

    async def override_http_client():
        async with httpx.AsyncClient(transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[get_http_client] = override_http_client


def test_api_key_optional_in_development_when_unset(
    app, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("APP_API_KEY", raising=False)
    get_settings.cache_clear()

    _mock_dependencies(app)
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_api_key_fails_closed_in_production_when_unset(
    app, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("APP_API_KEY", raising=False)
    get_settings.cache_clear()

    _mock_dependencies(app)
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_503"


def test_api_key_enforced_when_configured(
    app, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_API_KEY", "hydra-secret-key")
    get_settings.cache_clear()

    _mock_dependencies(app)
    try:
        missing_res = client.get("/api/v1/system/status")
        wrong_res = client.get("/api/v1/system/status", headers={"X-API-Key": "wrong"})
        valid_res = client.get(
            "/api/v1/system/status", headers={"X-API-Key": "hydra-secret-key"}
        )
    finally:
        app.dependency_overrides.clear()

    assert missing_res.status_code == 401
    assert missing_res.json()["error"]["code"] == "http_401"
    assert wrong_res.status_code == 401
    assert valid_res.status_code == 200


def test_unhandled_exception_returns_clean_json_without_traceback(app, client: TestClient) -> None:
    @app.get("/_test_boom")
    def boom() -> None:
        raise RuntimeError("secret-db-password-leak")

    response = client.get("/_test_boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected internal error occurred.",
        }
    }
    assert "secret-db-password-leak" not in response.text
