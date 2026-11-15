"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.security import verify_api_key
from app.db.session import get_db


async def get_http_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield a short-lived AsyncClient configured with the Ollama request timeout."""
    async with httpx.AsyncClient(timeout=settings.OLLAMA_REQUEST_TIMEOUT) as client:
        yield client


__all__ = [
    "get_db",
    "get_http_client",
    "get_settings",
    "verify_api_key",
]
