"""Common exception classes and FastAPI JSON exception handlers."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class HydraJobError(Exception):
    """Base domain/application error returning structured JSON responses."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "hydrajob_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


def _error_payload(
    *,
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


async def hydrajob_error_handler(request: Request, exc: HydraJobError) -> JSONResponse:
    """Handle application-level HydraJobError exceptions."""
    logger.warning(
        "Application error on %s %s: %s",
        request.method,
        request.url.path,
        exc.code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(code=exc.code, message=exc.message, details=exc.details),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle FastAPI/Starlette HTTPException with a consistent JSON shape."""
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    details = None if isinstance(exc.detail, str) else exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            code=f"http_{exc.status_code}",
            message=message,
            details=details,
        ),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors cleanly without internal tracebacks."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_payload(
            code="validation_error",
            message="Request validation failed.",
            details=exc.errors(),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all 500 handler that avoids leaking stack traces or secrets."""
    logger.exception(
        "Unhandled server exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_payload(
            code="internal_server_error",
            message="An unexpected internal error occurred.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all standard JSON exception handlers on the FastAPI app."""
    app.add_exception_handler(HydraJobError, hydrajob_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
