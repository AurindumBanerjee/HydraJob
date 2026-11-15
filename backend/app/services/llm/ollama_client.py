"""Ollama HTTP client abstraction with concurrency control, validation, and fallbacks."""

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import HydraJobError
from app.services.llm.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class OllamaClientError(HydraJobError):
    """Raised when Ollama fails and no deterministic fallback was supplied."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            message,
            code="ollama_client_error",
            status_code=503,
            details=details,
        )


class OllamaHealthStatus(BaseModel):
    """Result of probing Ollama /api/tags."""

    reachable: bool
    configured_model: str
    model_available: bool | None = None
    available_models: list[str] = []
    error: str | None = None


class OllamaStructuredResponse(BaseModel, Generic[T]):
    """Validated result returned by OllamaClient structured calls."""

    data: T
    used_fallback: bool
    model_name: str
    prompt_version: str
    attempts: int
    error: str | None = None
    raw_response: str | None = None


def _extract_json_text(raw_content: str) -> str:
    stripped = raw_content.strip()
    fence_match = _CODE_FENCE_RE.match(stripped)
    if fence_match:
        return fence_match.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    obj_match = _JSON_OBJECT_RE.search(stripped)
    if obj_match:
        return obj_match.group(0).strip()
    return stripped


def _extract_message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Ollama payload is not a JSON object.")
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    response_text = payload.get("response")
    if isinstance(response_text, str):
        return response_text
    raise ValueError("Ollama payload missing message.content or response string.")


class OllamaClient:
    """Thread-safe and async-safe Ollama client with bounded retries and Pydantic validation."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        prompt_version: str = PROMPT_VERSION,
        async_transport: httpx.AsyncBaseTransport | None = None,
        sync_transport: httpx.BaseTransport | None = None,
        async_client: httpx.AsyncClient | None = None,
        sync_client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        resolved_url = base_url if base_url is not None else settings.OLLAMA_BASE_URL
        self.base_url = resolved_url.strip().rstrip("/") or "http://ollama:11434"
        self.model = (model if model is not None else settings.OLLAMA_MODEL).strip()
        self.timeout = float(timeout if timeout is not None else settings.OLLAMA_REQUEST_TIMEOUT)
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.prompt_version = prompt_version

        self._async_transport = async_transport
        self._sync_transport = sync_transport
        self._external_async_client = async_client
        self._external_sync_client = sync_client

        # Enforce concurrency=1 to protect CPU/RAM-constrained local Ollama hosts.
        self._async_semaphore = asyncio.Semaphore(1)
        self._sync_lock = threading.Lock()

    def _model_matches(self, available_names: set[str]) -> bool | None:
        if not self.model:
            return None
        if self.model in available_names or f"{self.model}:latest" in available_names:
            return True
        if ":" not in self.model:
            return any(name.split(":", 1)[0] == self.model for name in available_names)
        return False

    def _parse_tags_response(self, response: httpx.Response) -> OllamaHealthStatus:
        if response.status_code != 200:
            return OllamaHealthStatus(
                reachable=False,
                configured_model=self.model,
                error=f"HTTP {response.status_code} from /api/tags",
            )
        try:
            payload = response.json()
        except ValueError:
            return OllamaHealthStatus(
                reachable=False,
                configured_model=self.model,
                error="Malformed JSON from /api/tags",
            )

        models_raw = payload.get("models", []) if isinstance(payload, dict) else []
        available = [
            str(item.get("name", "")).strip()
            for item in models_raw
            if isinstance(item, dict) and item.get("name")
        ]
        return OllamaHealthStatus(
            reachable=True,
            configured_model=self.model,
            model_available=self._model_matches(set(available)),
            available_models=available,
        )

    async def acheck_health(self) -> OllamaHealthStatus:
        """Probe Ollama /api/tags asynchronously without raising on network errors."""
        tags_url = f"{self.base_url}/api/tags"
        owns_client = self._external_async_client is None
        client = self._external_async_client or httpx.AsyncClient(
            timeout=self.timeout,
            transport=self._async_transport,
        )
        try:
            response = await client.get(tags_url, timeout=self.timeout)
            return self._parse_tags_response(response)
        except httpx.HTTPError as exc:
            logger.warning("Ollama async health check failed: %s", type(exc).__name__)
            return OllamaHealthStatus(
                reachable=False,
                configured_model=self.model,
                error=type(exc).__name__,
            )
        finally:
            if owns_client:
                await client.aclose()

    def check_health(self) -> OllamaHealthStatus:
        """Probe Ollama /api/tags synchronously without raising on network errors."""
        tags_url = f"{self.base_url}/api/tags"
        owns_client = self._external_sync_client is None
        client = self._external_sync_client or httpx.Client(
            timeout=self.timeout,
            transport=self._sync_transport,
        )
        try:
            response = client.get(tags_url, timeout=self.timeout)
            return self._parse_tags_response(response)
        except httpx.HTTPError as exc:
            logger.warning("Ollama sync health check failed: %s", type(exc).__name__)
            return OllamaHealthStatus(
                reachable=False,
                configured_model=self.model,
                error=type(exc).__name__,
            )
        finally:
            if owns_client:
                client.close()

    def _build_chat_payload(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
    ) -> dict[str, object]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }

    def _validate_response(
        self,
        response: httpx.Response,
        response_model: type[T],
    ) -> tuple[T, str]:
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Ollama HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        payload = response.json()
        raw_content = _extract_message_content(payload)
        cleaned_json = _extract_json_text(raw_content)
        parsed_obj = json.loads(cleaned_json)
        validated = response_model.model_validate(parsed_obj)
        return validated, raw_content

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 429} or status_code >= 500

    def _fallback_or_raise(
        self,
        *,
        fallback_factory: Callable[[], T] | None,
        prompt_version: str,
        attempts: int,
        error_msg: str,
        raw_response: str | None = None,
    ) -> OllamaStructuredResponse[T]:
        if fallback_factory is None:
            raise OllamaClientError(
                f"Ollama structured generation failed: {error_msg}",
                details={"attempts": attempts, "prompt_version": prompt_version},
            )
        return OllamaStructuredResponse(
            data=fallback_factory(),
            used_fallback=True,
            model_name=self.model or "deterministic-fallback",
            prompt_version=prompt_version,
            attempts=attempts,
            error=error_msg,
            raw_response=raw_response,
        )

    async def agenerate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        fallback_factory: Callable[[], T] | None = None,
        temperature: float = 0.0,
        prompt_version: str | None = None,
    ) -> OllamaStructuredResponse[T]:
        """Call Ollama /api/chat with semaphore=1, retries, schema validation, and fallback."""
        effective_version = prompt_version or self.prompt_version
        if not self.model:
            return self._fallback_or_raise(
                fallback_factory=fallback_factory,
                prompt_version=effective_version,
                attempts=0,
                error_msg="OLLAMA_MODEL is not configured",
            )

        chat_url = f"{self.base_url}/api/chat"
        payload = self._build_chat_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        max_attempts = 1 + self.max_retries
        last_error = "unknown error"

        async with self._async_semaphore:
            owns_client = self._external_async_client is None
            client = self._external_async_client or httpx.AsyncClient(
                timeout=self.timeout,
                transport=self._async_transport,
            )
            try:
                for attempt in range(1, max_attempts + 1):
                    try:
                        response = await client.post(chat_url, json=payload, timeout=self.timeout)
                        validated, raw_content = self._validate_response(response, response_model)
                        return OllamaStructuredResponse(
                            data=validated,
                            used_fallback=False,
                            model_name=self.model,
                            prompt_version=effective_version,
                            attempts=attempt,
                            raw_response=raw_content,
                        )
                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        last_error = f"HTTP {status_code}"
                        logger.warning("Ollama HTTP error (attempt %s): %s", attempt, status_code)
                        if not self._is_retryable_status(status_code):
                            return self._fallback_or_raise(
                                fallback_factory=fallback_factory,
                                prompt_version=effective_version,
                                attempts=attempt,
                                error_msg=last_error,
                            )
                    except (httpx.HTTPError, ValueError, ValidationError) as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
                        logger.warning(
                            "Ollama structured call error (attempt %s/%s): %s",
                            attempt,
                            max_attempts,
                            type(exc).__name__,
                        )

                    if attempt < max_attempts and self.backoff_seconds > 0:
                        await asyncio.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            finally:
                if owns_client:
                    await client.aclose()

        return self._fallback_or_raise(
            fallback_factory=fallback_factory,
            prompt_version=effective_version,
            attempts=max_attempts,
            error_msg=last_error,
        )

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        fallback_factory: Callable[[], T] | None = None,
        temperature: float = 0.0,
        prompt_version: str | None = None,
    ) -> OllamaStructuredResponse[T]:
        """Call Ollama /api/chat synchronously with threading.Lock, retries, and fallback."""
        effective_version = prompt_version or self.prompt_version
        if not self.model:
            return self._fallback_or_raise(
                fallback_factory=fallback_factory,
                prompt_version=effective_version,
                attempts=0,
                error_msg="OLLAMA_MODEL is not configured",
            )

        chat_url = f"{self.base_url}/api/chat"
        payload = self._build_chat_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        max_attempts = 1 + self.max_retries
        last_error = "unknown error"

        with self._sync_lock:
            owns_client = self._external_sync_client is None
            client = self._external_sync_client or httpx.Client(
                timeout=self.timeout,
                transport=self._sync_transport,
            )
            try:
                for attempt in range(1, max_attempts + 1):
                    try:
                        response = client.post(chat_url, json=payload, timeout=self.timeout)
                        validated, raw_content = self._validate_response(response, response_model)
                        return OllamaStructuredResponse(
                            data=validated,
                            used_fallback=False,
                            model_name=self.model,
                            prompt_version=effective_version,
                            attempts=attempt,
                            raw_response=raw_content,
                        )
                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        last_error = f"HTTP {status_code}"
                        logger.warning("Ollama HTTP error (attempt %s): %s", attempt, status_code)
                        if not self._is_retryable_status(status_code):
                            return self._fallback_or_raise(
                                fallback_factory=fallback_factory,
                                prompt_version=effective_version,
                                attempts=attempt,
                                error_msg=last_error,
                            )
                    except (httpx.HTTPError, ValueError, ValidationError) as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
                        logger.warning(
                            "Ollama structured call error (attempt %s/%s): %s",
                            attempt,
                            max_attempts,
                            type(exc).__name__,
                        )

                    if attempt < max_attempts and self.backoff_seconds > 0:
                        time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            finally:
                if owns_client:
                    client.close()

        return self._fallback_or_raise(
            fallback_factory=fallback_factory,
            prompt_version=effective_version,
            attempts=max_attempts,
            error_msg=last_error,
        )
