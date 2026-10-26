"""Request IDs and exception-to-HTTP mapping.

Every error leaves the API as an ``ErrorResponse`` carrying the request ID,
which is also echoed in the ``X-Request-ID`` response header.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.llm.errors import OllamaConnectionError, OllamaResponseError

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a request ID (incoming header or new UUID) to state and response."""
    request.state.request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


def _error_response(request: Request, status_code: int, error: str, detail: str) -> JSONResponse:
    """Log and build a structured error response carrying the request ID."""
    rid = getattr(request.state, "request_id", None)
    logger.warning("request_id=%s %s: %s", rid, error, detail)
    body = ErrorResponse(error=error, detail=detail, request_id=rid).model_dump()
    headers = {REQUEST_ID_HEADER: rid} if rid else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Return 422 with the first validation message."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = errors[0].get("msg", "invalid request") if errors else "invalid request"
    return _error_response(request, 422, "validation_error", detail)


async def _ollama_unreachable(request: Request, exc: Exception) -> JSONResponse:
    """Return 503 when Ollama cannot be reached."""
    return _error_response(request, 503, "ollama_unreachable", str(exc))


async def _ollama_bad_response(request: Request, exc: Exception) -> JSONResponse:
    """Return 502 when Ollama answers with an error or malformed body."""
    return _error_response(request, 502, "ollama_bad_response", str(exc))


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback and return a generic 500."""
    logger.exception("unhandled exception", exc_info=exc)
    return _error_response(
        request, 500, "internal_error", "An unexpected error occurred. Check server logs."
    )


def install_error_handling(app: FastAPI) -> None:
    """Register the request-ID middleware and all exception handlers on ``app``."""
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(OllamaConnectionError, _ollama_unreachable)
    app.add_exception_handler(OllamaResponseError, _ollama_bad_response)
    app.add_exception_handler(Exception, _unhandled)
