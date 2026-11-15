"""Service-level health and system diagnostics helpers."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OllamaCheckResult:
    """Result of probing the configured Ollama instance."""

    reachable: bool
    model_available: bool | None = None


async def check_ollama_reachability(
    base_url: str,
    timeout: float,
    configured_model: str = "",
    client: httpx.AsyncClient | None = None,
) -> OllamaCheckResult:
    """Probe Ollama /api/tags without raising on connection or HTTP errors."""
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout)

    try:
        response = await http_client.get(tags_url, timeout=timeout)
        if response.status_code != 200:
            logger.warning("Ollama /api/tags returned HTTP %s", response.status_code)
            return OllamaCheckResult(reachable=False, model_available=None)

        model_available: bool | None = None
        if configured_model:
            try:
                payload = response.json()
                models = payload.get("models", []) if isinstance(payload, dict) else []
                available_names = {
                    str(item.get("name", "")).strip()
                    for item in models
                    if isinstance(item, dict) and item.get("name")
                }
                model_available = (
                    configured_model in available_names
                    or f"{configured_model}:latest" in available_names
                )
            except ValueError:
                model_available = None

        return OllamaCheckResult(reachable=True, model_available=model_available)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Ollama reachability check failed: %s", type(exc).__name__)
        return OllamaCheckResult(reachable=False, model_available=None)
    finally:
        if owns_client:
            await http_client.aclose()
