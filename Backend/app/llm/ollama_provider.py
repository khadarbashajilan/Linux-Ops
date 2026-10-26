"""Ollama LLM provider.

Calls a local Ollama instance (Docker or bare metal) via ``/api/chat``.

- One ``httpx.AsyncClient`` per provider, reused across calls.
- Split connect/read timeouts.
- Retry with exponential backoff on connection failures and 5xx responses.
- Pydantic validation of the response body.
"""

import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.llm.base import ChatMessage, LLMResponse, ToolCall, ToolSchema
from app.llm.errors import OllamaConnectionError, OllamaResponseError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({500, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    """Return True for errors worth retrying: unreachable server or transient 5xx."""
    if isinstance(exc, OllamaConnectionError):
        return True
    return isinstance(exc, OllamaResponseError) and exc.status_code in _RETRYABLE_STATUS_CODES


def _log_retry(state: RetryCallState) -> None:
    """Log a warning before each retry sleep."""
    exc = state.outcome.exception() if state.outcome else None
    sleep = state.next_action.sleep if state.next_action else 0.0
    logger.warning(
        "ollama call failed (attempt %d), retrying in %.1fs: %s",
        state.attempt_number,
        sleep,
        exc,
    )


class _OllamaFunction(BaseModel):
    """Function part of a tool call in Ollama's response."""

    name: str = ""
    arguments: dict[str, Any] | str = Field(default_factory=dict)


class _OllamaToolCall(BaseModel):
    """One tool call in Ollama's response."""

    id: str = ""
    function: _OllamaFunction


class _OllamaMessage(BaseModel):
    """Assistant message in Ollama's response."""

    content: str | None = ""
    tool_calls: list[_OllamaToolCall] | None = None


class _OllamaResponse(BaseModel):
    """Top-level shape of Ollama's ``/api/chat`` response."""

    message: _OllamaMessage | None = None


def _raise_for_status(resp: httpx.Response) -> None:
    """Raise ``OllamaResponseError`` for any 4xx/5xx response."""
    if resp.is_error:
        raise OllamaResponseError(resp.status_code, resp.text[:200])


def _parse_arguments(raw: dict[str, Any] | str) -> dict[str, Any]:
    """Normalise tool arguments that may arrive as a dict or a JSON string."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class OllamaProvider:
    """Provider calling a local Ollama instance with retry and timeout support."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Create the provider and its shared HTTP client.

        Args:
            settings: application settings; defaults to the cached singleton.

        """
        self._settings = settings or get_settings()
        self._base_url = self._settings.ollama_base_url.rstrip("/")
        self._model = self._settings.ollama_model
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=self._settings.ollama_timeout_connect,
                read=self._settings.ollama_timeout_read,
                write=30.0,
                pool=30.0,
            ),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    @property
    def model(self) -> str:
        """Return the configured Ollama model name."""
        return self._model

    async def aclose(self) -> None:
        """Close the shared HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send one request, translating transport failures into domain errors.

        Args:
            method: HTTP method.
            path: path relative to the Ollama base URL.
            **kwargs: forwarded to ``httpx.AsyncClient.request``.

        Returns:
            The raw HTTP response (any status code).

        Raises:
            OllamaConnectionError: when the server is unreachable or times out.

        """
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(self._base_url, str(exc) or "connection refused") from exc
        except httpx.TimeoutException as exc:
            raise OllamaConnectionError(
                self._base_url,
                f"timeout after {self._settings.ollama_timeout_connect}s connect / "
                f"{self._settings.ollama_timeout_read}s read",
            ) from exc

    async def _call(self, payload: dict[str, Any]) -> _OllamaResponse:
        """Make a single ``/api/chat`` call and validate the response.

        Args:
            payload: the request body.

        Returns:
            The validated Ollama response.

        Raises:
            OllamaConnectionError: when the server is unreachable or times out.
            OllamaResponseError: on a non-200 status or malformed body.

        """
        resp = await self._request("POST", "/api/chat", json=payload)
        if resp.status_code == 404:
            raise OllamaResponseError(404, f"model {self._model!r} not found — pull it first")
        _raise_for_status(resp)
        try:
            return _OllamaResponse.model_validate(resp.json())
        except (json.JSONDecodeError, ValidationError) as exc:
            raise OllamaResponseError(resp.status_code, f"unexpected response: {exc}") from exc

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against the local Ollama instance.

        Args:
            messages: conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The parsed model response.

        Raises:
            OllamaConnectionError: when Ollama is unreachable after all retries.
            OllamaResponseError: on a non-200 status or malformed body.

        """
        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        retrying = AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._settings.ollama_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            before_sleep=_log_retry,
            reraise=True,
        )
        response = await retrying(self._call, payload)

        msg = response.message or _OllamaMessage()
        tool_calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=_parse_arguments(call.function.arguments),
            )
            for call in msg.tool_calls or []
        ]
        return LLMResponse(content=msg.content or "", tool_calls=tool_calls)

    async def health_check(self) -> float:
        """Ping Ollama's version endpoint (no model inference).

        Returns:
            Round-trip latency in milliseconds.

        Raises:
            OllamaConnectionError: when the server cannot be reached.
            OllamaResponseError: when the server answers with an error status.

        """
        start = time.perf_counter()
        resp = await self._request("GET", "/api/version")
        _raise_for_status(resp)
        return (time.perf_counter() - start) * 1000
