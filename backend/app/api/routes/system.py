"""Authenticated system diagnostics routes."""

from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_http_client, get_settings, verify_api_key
from app.core.config import Settings
from app.db.session import check_database_connectivity
from app.schemas.system import (
    OllamaServiceHealth,
    ServiceHealth,
    SystemServicesStatus,
    SystemStatusResponse,
    TimestampInfo,
)
from app.services.system_status import check_ollama_reachability

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_system_status(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> SystemStatusResponse:
    """Return PostgreSQL and Ollama reachability plus UTC and local timestamps."""
    db_ok = check_database_connectivity(db)
    ollama_result = await check_ollama_reachability(
        base_url=settings.OLLAMA_BASE_URL,
        timeout=settings.OLLAMA_REQUEST_TIMEOUT,
        configured_model=settings.OLLAMA_MODEL,
        client=http_client,
    )

    now_utc = datetime.now(UTC)
    now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    local_tz = ZoneInfo(settings.TZ)
    now_local = now_utc.astimezone(local_tz)

    overall_status = "ok" if (db_ok and ollama_result.reachable) else "degraded"

    return SystemStatusResponse(
        status=overall_status,
        environment=settings.APP_ENV,
        timestamps=TimestampInfo(
            utc=now_utc.isoformat(),
            asia_kolkata=now_ist.isoformat(),
            local=now_local.isoformat(),
            timezone=settings.TZ,
        ),
        services=SystemServicesStatus(
            api=ServiceHealth(status="ok"),
            database=ServiceHealth(status="ok" if db_ok else "unavailable"),
            ollama=OllamaServiceHealth(
                status="ok" if ollama_result.reachable else "unavailable",
                model=settings.OLLAMA_MODEL or None,
                model_available=ollama_result.model_available,
            ),
        ),
    )
