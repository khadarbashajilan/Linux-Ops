"""Errors raised by the Ollama provider."""


class OllamaConnectionError(RuntimeError):
    """Raised when Ollama is unreachable, refuses the connection, or times out."""

    def __init__(self, base_url: str, detail: str) -> None:
        """Initialise with the base URL and a specific reason.

        Args:
            base_url: the Ollama base URL that was unreachable.
            detail: the underlying reason (e.g. "connection refused").

        """
        super().__init__(f"Ollama not reachable at {base_url}: {detail}")
        self.base_url = base_url
        self.detail = detail


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an error status or an unparseable body."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialise with the HTTP status code and reason.

        Args:
            status_code: the HTTP status code returned by Ollama.
            detail: the underlying reason.

        """
        super().__init__(f"Ollama returned {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
