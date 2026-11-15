"""Tests for /health and /health/ready endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_db
from app.core.config import get_settings


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_succeeds_when_database_reachable(app, client: TestClient) -> None:
    mock_db = MagicMock()
    mock_db.execute.return_value = 1

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    mock_db.execute.assert_called_once()


def test_health_ready_returns_503_when_database_fails(app, client: TestClient) -> None:
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("conn refused"))

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}


def test_health_endpoints_stay_open_when_api_key_is_set(
    app, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_API_KEY", "super-secret-api-key")
    get_settings.cache_clear()

    mock_db = MagicMock()
    mock_db.execute.return_value = 1
    app.dependency_overrides[get_db] = lambda: (yield mock_db)
    try:
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 200
    finally:
        app.dependency_overrides.clear()
