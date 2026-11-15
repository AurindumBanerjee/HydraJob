"""SQLAlchemy 2.x engine, session factory, and connectivity helper."""

import logging
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine from configured settings or an explicit URL."""
    url = database_url or get_settings().sqlalchemy_database_url
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **engine_kwargs)


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure closure after request completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connectivity(db: Session) -> bool:
    """Verify database connectivity using SELECT 1 without exposing credentials."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning("Database connectivity check failed: %s", type(exc).__name__)
        return False
