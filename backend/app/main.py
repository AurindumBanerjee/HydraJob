"""FastAPI application entrypoint and lifecycle wiring."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.applications import router as applications_router
from app.api.routes.companies import router as companies_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.emails import router as emails_router
from app.api.routes.evaluations import router as evaluations_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.profile import router as profile_router
from app.api.routes.searches import router as searches_router
from app.api.routes.sources_lifecycle import router as sources_lifecycle_router
from app.api.routes.system import router as system_router
from app.api.routes.tasks import router as tasks_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Log startup/shutdown events and dispose database pools cleanly."""
    settings = get_settings()
    logger.info(
        "Starting %s backend (env=%s, tz=%s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.TZ,
    )
    try:
        yield
    finally:
        engine.dispose()
        logger.info("Stopped %s backend", settings.APP_NAME)


def create_app() -> FastAPI:
    """Create and configure the HydraJob FastAPI application."""
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, settings=settings)

    application = FastAPI(
        title=f"{settings.APP_NAME} API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(application)

    application.include_router(health_router)
    application.include_router(system_router, prefix=settings.API_V1_PREFIX)
    application.include_router(profile_router, prefix=settings.API_V1_PREFIX)
    application.include_router(sources_lifecycle_router, prefix=settings.API_V1_PREFIX)
    application.include_router(companies_router, prefix=settings.API_V1_PREFIX)
    application.include_router(ingestion_router, prefix=settings.API_V1_PREFIX)
    application.include_router(evaluations_router, prefix=settings.API_V1_PREFIX)
    application.include_router(jobs_router, prefix=settings.API_V1_PREFIX)
    application.include_router(applications_router, prefix=settings.API_V1_PREFIX)
    application.include_router(tasks_router, prefix=settings.API_V1_PREFIX)
    application.include_router(searches_router, prefix=settings.API_V1_PREFIX)
    application.include_router(discovery_router, prefix=settings.API_V1_PREFIX)
    application.include_router(emails_router, prefix=settings.API_V1_PREFIX)

    return application


app = create_app()
