"""Shared pytest fixtures for HydraJob backend tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep settings isolated per test and clear lru_cache before/after."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Provide an isolated per-test SQLite database session with all tables."""
    db_file = tmp_path / "test_hydrajob.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def app(db_session: Session):
    """Return a fresh FastAPI app instance wired to the isolated test DB."""
    application = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    """Return a TestClient bound to the test FastAPI app."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
