"""Unified error response helpers for MemOS API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

logger = logging.getLogger("memos.api")


def error_response(
    message: str,
    *,
    code: str = "ERROR",
    status_code: int = 400,
) -> JSONResponse:
    """Return a standardised error JSON response.

    Args:
        message: Human-readable error description (safe for clients).
        code: Machine-readable error code (e.g. ``NOT_FOUND``, ``VALIDATION``).
        status_code: HTTP status code.

    Returns:
        JSONResponse with ``{"status": "error", "message": ..., "code": ...}``.
    """
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message, "code": code},
    )


def not_found(message: str = "Resource not found", **kwargs: Any) -> JSONResponse:
    """Return a 404 Not Found response."""
    return error_response(message, code="NOT_FOUND", status_code=404, **kwargs)


def validation_error(message: str = "Invalid request", **kwargs: Any) -> JSONResponse:
    """Return a 422 Validation Error response."""
    return error_response(message, code="VALIDATION", status_code=422, **kwargs)


def internal_error(message: str = "Internal server error", **kwargs: Any) -> JSONResponse:
    """Return a 500 Internal Server Error response.

    Prefer ``handle_exception`` which also logs the full traceback.
    """
    return error_response(message, code="INTERNAL_ERROR", status_code=500, **kwargs)


def handle_exception(exc: Exception, context: str = "") -> JSONResponse:
    """Log an exception and return a safe 500 response.

    Logs the full exception server-side but returns only a generic
    message to the client to prevent information leakage.

    Args:
        exc: The caught exception.
        context: Optional context string (e.g. route name) for the log.

    Returns:
        JSONResponse with status 500 and a generic message.
    """
    logger.error("Error in %s: %s", context or "request", exc, exc_info=True)
    return internal_error("Internal server error")
