"""Service layer for the HydraJob Streamlit dashboard."""

from services.api_client import (
    DEFAULT_API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    ApiResponse,
    HealthCheckResult,
    HydraJobApiClient,
    ReadinessCheckResult,
    ServiceStatusInfo,
    SystemOverview,
    SystemStatusResult,
    build_api_client_from_env,
)
from services.time_utils import (
    IST_ZONE,
    format_kolkata_timestamp,
    now_kolkata_formatted,
    now_kolkata_iso,
)

__all__ = [
    "DEFAULT_API_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "IST_ZONE",
    "ApiResponse",
    "HealthCheckResult",
    "HydraJobApiClient",
    "ReadinessCheckResult",
    "ServiceStatusInfo",
    "SystemOverview",
    "SystemStatusResult",
    "build_api_client_from_env",
    "format_kolkata_timestamp",
    "now_kolkata_formatted",
    "now_kolkata_iso",
]
