"""Integration tests for /api/v1/system/status and Alembic baseline."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError

from alembic import command
from app.api.dependencies import get_db, get_http_client
from app.core.config import get_settings


def test_system_status_all_healthy(
    app, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://hydrajob:verysecretpw@postgres:5432/hydrajob")
    monkeypatch.setenv("APP_SECRET_KEY", "super-secret-value")
    get_settings.cache_clear()

    mock_db = MagicMock()
    mock_db.execute.return_value = 1

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})

    transport = httpx.MockTransport(ollama_handler)

    async def override_http_client():
        async with httpx.AsyncClient(transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[get_db] = lambda: (yield mock_db)
    app.dependency_overrides[get_http_client] = override_http_client
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["services"]["api"]["status"] == "ok"
    assert payload["services"]["database"]["status"] == "ok"
    assert payload["services"]["ollama"] == {
        "status": "ok",
        "model": "llama3.1:8b",
        "model_available": True,
    }

    assert payload["timestamps"]["timezone"] == "Asia/Kolkata"
    utc_dt = datetime.fromisoformat(payload["timestamps"]["utc"])
    ist_dt = datetime.fromisoformat(payload["timestamps"]["asia_kolkata"])
    local_dt = datetime.fromisoformat(payload["timestamps"]["local"])
    assert utc_dt.utcoffset().total_seconds() == 0
    assert ist_dt.utcoffset().total_seconds() == 5 * 3600 + 30 * 60
    assert local_dt.utcoffset().total_seconds() == 5 * 3600 + 30 * 60

    assert "verysecretpw" not in response.text
    assert "super-secret-value" not in response.text


def test_system_status_degraded_when_ollama_unreachable(app, client: TestClient) -> None:
    mock_db = MagicMock()
    mock_db.execute.return_value = 1

    def failing_ollama(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(failing_ollama)

    async def override_http_client():
        async with httpx.AsyncClient(transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[get_db] = lambda: (yield mock_db)
    app.dependency_overrides[get_http_client] = override_http_client
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["services"]["database"]["status"] == "ok"
    assert payload["services"]["ollama"]["status"] == "unavailable"
    assert payload["services"]["ollama"]["model_available"] is None


def test_system_status_degraded_when_database_unreachable(app, client: TestClient) -> None:
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": []})
    )

    async def override_http_client():
        async with httpx.AsyncClient(transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[get_db] = lambda: (yield mock_db)
    app.dependency_overrides[get_http_client] = override_http_client
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["services"]["database"]["status"] == "unavailable"
    assert payload["services"]["ollama"]["status"] == "ok"


def test_alembic_baseline_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    db_path = tmp_path / "alembic_test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    assert script.get_current_head() == "20261114_0002"

    command.upgrade(alembic_cfg, "head")
    engine = create_engine(db_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "alembic_version" in tables
    finally:
        engine.dispose()

    command.downgrade(alembic_cfg, "base")
