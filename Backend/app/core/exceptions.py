"""Custom exceptions and structured error response schemas for the API."""

from pydantic import BaseModel, Field


class OllamaConnectionError(RuntimeError):
    """Raised when Ollama is unreachable, times out on connect, or refuses connection."""

    def __init__(self, base_url: str, detail: str) -> None:
        """Initialise with the base URL and a specific reason.

        Args:
            base_url: the Ollama base URL that was unreachable.
            detail: the underlying reason (e.g. "Connection refused").

        """
        super().__init__(f"Ollama not reachable at {base_url}: {detail}")
        self.base_url = base_url
        self.detail = detail


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns a non-200 response or an unparseable body."""

    def __init__(self, status_code: int | None, detail: str) -> None:
        """Initialise with the HTTP status code and reason.

        Args:
            status_code: the HTTP status code returned by Ollama.
            detail: the underlying reason.

        """
        super().__init__(f"Ollama returned {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class ErrorResponse(BaseModel):
    """Every error response from the API follows this shape."""

    error: str = Field(..., description="Short machine-readable error code.")
    detail: str = Field(..., description="Human-readable message.")
    request_id: str | None = Field(default=None, description="Correlates to server logs.")
