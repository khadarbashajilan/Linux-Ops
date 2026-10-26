"""HTTP client for the LinuxOps backend API."""

from types import TracebackType
from typing import Any, Self

import httpx

CHAT_TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=10.0, pool=5.0)


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error response."""


class LinuxOpsClient:
    """Thin HTTP client — all agent logic lives in the backend."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create the client.

        Args:
            base_url: backend API base URL.
            token: optional bearer token.
            transport: optional custom transport (used by tests).

        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=CHAT_TIMEOUT, transport=transport
        )

    def __enter__(self) -> Self:
        """Return self for use in a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a request and return the JSON body.

        Raises:
            BackendError: on connection failure or a non-2xx response, with the
                backend's ``detail`` message when available.

        """
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise BackendError(f"backend timed out at {self.base_url}") from exc
        except httpx.TransportError as exc:
            raise BackendError(
                f"backend unreachable at {self.base_url} — is it running? "
                "(cd Backend && uv run uvicorn app.main:app)"
            ) from exc
        if resp.is_error:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise BackendError(f"{resp.status_code}: {detail}")
        return resp.json()

    def chat(self, message: str) -> dict[str, Any]:
        """Send a message to the agent.

        Args:
            message: the user's message.

        Returns:
            Dict with ``response`` (str) and ``tool_calls`` (list of tool names).

        """
        return self._request("POST", "/chat", json={"message": message})

    def health(self) -> dict[str, Any]:
        """Fetch backend health.

        Returns:
            Dict with ``status``, ``ollama``, ``ollama_latency_ms`` and ``model``.

        """
        return self._request("GET", "/health")
