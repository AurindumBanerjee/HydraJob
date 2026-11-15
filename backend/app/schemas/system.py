"""Pydantic schemas for health and system status endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]


class TimestampInfo(BaseModel):
    """Current UTC and Asia/Kolkata timestamps."""

    utc: str
    asia_kolkata: str
    local: str
    timezone: str


class ServiceHealth(BaseModel):
    """Generic service reachability status."""

    status: Literal["ok", "unavailable"]


class OllamaServiceHealth(BaseModel):
    """Ollama reachability and configured model status."""

    status: Literal["ok", "unavailable"]
    model: str | None = None
    model_available: bool | None = None


class SystemServicesStatus(BaseModel):
    """Aggregated status of HydraJob core services."""

    api: ServiceHealth
    database: ServiceHealth
    ollama: OllamaServiceHealth


class SystemStatusResponse(BaseModel):
    """Response payload for GET /api/v1/system/status."""

    status: Literal["ok", "degraded"]
    environment: str
    timestamps: TimestampInfo
    services: SystemServicesStatus
