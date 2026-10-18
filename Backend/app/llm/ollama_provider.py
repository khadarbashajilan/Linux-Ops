"""Ollama LLM provider.

Calls a local Ollama instance via its REST /api/chat endpoint.
Assumes Docker (or bare-metal Ollama) is already running with the configured model.

Features:
- Shared httpx.AsyncClient for connection reuse.
- Split connect/read timeouts.
- Retry with exponential backoff on transient errors (503, 500, timeouts).
- Pydantic response validation.
- Custom exceptions for connection vs response failures.
"""

import json
import logging

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import OllamaConnectionError, OllamaResponseError
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSchema,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {503, 500, 504}


def _is_retryable(exc: BaseException) -> bool:
    """Return True for errors that should trigger a retry."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _RETRYABLE_STATUS_CODES
    ):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    return False


class _OllamaMessage(BaseModel):
    """Minimal validation model for Ollama's /api/chat response."""

    role: str | None = None
    content: str | None = ""
    tool_calls: list[dict] | None = Field(default_factory=list)


class _OllamaResponse(BaseModel):
    """Top-level validation for Ollama's /api/chat response."""

    model: str | None = None
    message: _OllamaMessage | None = None
    done: bool | None = None


class OllamaProvider:
    """Provider calling a local Ollama instance with retry and timeout support."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise with the base URL, model, and timeout settings."""
        self._settings = settings or get_settings()
        self._base_url = self._settings.ollama_base_url.rstrip("/")
        self._model = self._settings.ollama_model
        self._timeout = httpx.Timeout(
            connect=self._settings.ollama_timeout_connect,
            read=self._settings.ollama_timeout_read,
            pool=30.0,
            write=30.0,
        )
        self._max_retries = self._settings.ollama_max_retries

    def _client(self) -> httpx.AsyncClient:
        """Return a shared httpx client with connection reuse."""
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def _call(self, payload: dict) -> _OllamaResponse:
        """Make a single HTTP call to Ollama, raising on connection/response errors.

        Args:
            payload: the request body.

        Returns:
            The parsed and validated Ollama response.

        Raises:
            OllamaConnectionError: when the server is unreachable or times out on connect.
            OllamaResponseError: when Ollama returns a non-200 or malformed body.

        """
        client = self._client()
        try:
            resp = await client.post(
                "/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                self._base_url,
                str(exc) or "Connection refused",
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaConnectionError(
                self._base_url,
                (
                    f"timeout after "
                    f"{self._settings.ollama_timeout_connect}s connect / "
                    f"{self._settings.ollama_timeout_read}s read"
                ),
            ) from exc
        finally:
            await client.aclose()

        if resp.status_code >= 500:
            raise OllamaResponseError(
                resp.status_code,
                f"Ollama server error: {resp.text[:200]}",
            )
        if resp.status_code == 404:
            raise OllamaResponseError(
                resp.status_code,
                f"model {self._model!r} not found at Ollama — pull it first",
            )
        if resp.status_code >= 400:
            raise OllamaResponseError(
                resp.status_code,
                f"Ollama request rejected: {resp.text[:200]}",
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise OllamaResponseError(resp.status_code, f"non-JSON response: {exc}") from exc

        try:
            return _OllamaResponse.model_validate(data)
        except Exception as exc:
            raise OllamaResponseError(
                resp.status_code,
                f"unexpected response shape: {exc}",
            ) from exc

    @property
    def _retry_decorator(self):
        """Return a tenacity retry decorator for Ollama transient errors."""
        return retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
            before_sleep=lambda retry_state: logger.warning(
                "Ollama call failed (attempt %d/%d), retrying in %.1fs: %s",
                retry_state.attempt_number,
                self._max_retries,
                retry_state.next_action.sleep if retry_state.next_action else 0,
                retry_state.outcome.exception(),
            ),
        )

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against the local Ollama instance.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The parsed model response.

        Raises:
            OllamaConnectionError: when Ollama is unreachable after all retries.
            OllamaResponseError: when Ollama returns a non-200 or malformed body.
            ProviderError: on unexpected internal errors.

        """
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        retry_call = self._retry_decorator(self._call)

        try:
            response = await retry_call(payload)
        except OllamaConnectionError:
            raise
        except OllamaResponseError:
            raise
        except Exception as exc:
            logger.error("unexpected Ollama error: %s", exc)
            raise ProviderError(f"ollama: unexpected error: {exc}") from exc

        tool_calls = []
        msg = response.message
        if msg and msg.tool_calls:
            for call in msg.tool_calls:
                func = call.get("function") or {}
                try:
                    raw_args = func.get("arguments")
                    arguments = (
                        raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
                    )
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    ToolCall(
                        id=call.get("id", ""),
                        name=func.get("name", ""),
                        arguments=arguments,
                    )
                )
        return LLMResponse(content=msg.content if msg else None, tool_calls=tool_calls)

    async def health_check(self) -> tuple[bool, float]:
        """Check if Ollama is reachable and responsive.

        Returns:
            A tuple of (is_healthy, latency_ms).

        Raises:
            OllamaConnectionError: when the server cannot be reached.

        """
        import time

        client = self._client()
        start = time.perf_counter()
        try:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                },
                headers={"Content-Type": "application/json"},
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return (resp.status_code == 200, latency_ms)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OllamaConnectionError(self._base_url, str(exc)) from exc
        finally:
            await client.aclose()
