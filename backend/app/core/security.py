"""API key authentication dependency for protected backend routes."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    provided_key: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str | None:
    """Validate X-API-Key when APP_API_KEY is configured.

    In development/test environments, access is permitted when APP_API_KEY is unset.
    In non-development environments, a missing APP_API_KEY fails closed.
    """
    configured_key = settings.APP_API_KEY
    if not configured_key:
        if settings.is_development:
            return None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication is not configured on the server.",
        )

    if not provided_key or not secrets.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

    return "authenticated"
