"""Google Gemini LLM provider (tier 3).

Uses the ``google-genai`` SDK. Gemini's native tool format differs from the
OpenAI shape, so this provider translates messages and tool schemas into
Gemini contents and function declarations.
"""

import logging

from google import genai
from google.genai import types

from app.core.config import Settings, get_settings
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSchema,
)

logger = logging.getLogger(__name__)


def _to_gemini_contents(messages: list[ChatMessage]) -> list[types.Content]:
    """Convert OpenAI-style messages to Gemini contents.

    Args:
        messages: OpenAI-style conversation history.

    Returns:
        A list of Gemini ``Content`` objects.

    """
    contents: list[types.Content] = []
    for msg in messages:
        role = msg["role"]
        parts: list[types.Part] = []
        if msg.get("content"):
            parts.append(types.Part(text=msg["content"]))
        for call in msg.get("tool_calls") or []:
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        name=call["function"]["name"],
                        args=_safe_json(call["function"].get("arguments")),
                    )
                )
            )
        if msg.get("tool_call_id"):
            parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=msg.get("name", ""),
                        response={"result": msg.get("content")},
                    )
                )
            )
        if not parts:
            continue
        gemini_role = "model" if role in ("assistant", "model") else "user"
        contents.append(types.Content(role=gemini_role, parts=parts))
    return contents


def _safe_json(raw: str | dict | None) -> dict:
    """Parse a possibly-string JSON argument blob into a dict."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


class GeminiProvider:
    """Provider calling the Gemini Developer API via google-genai."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the async Gemini client from settings."""
        self._settings = settings or get_settings()
        self._client = genai.Client(api_key=self._settings.gemini_api_key.get_secret_value())

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against Gemini.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas to expose as function declarations.

        Returns:
            The parsed model response.

        Raises:
            ProviderError: on API failures so the router can log/deny.

        """
        tool_dicts: list[dict] = []
        if tools:
            declarations = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"].get("parameters"),
                }
                for t in tools
            ]
            tool_dicts = [{"function_declarations": declarations}]
        config = types.GenerateContentConfig(
            tools=tool_dicts if tool_dicts else None,
            temperature=0.7,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._settings.gemini_model,
                contents=_to_gemini_contents(messages),
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 — SDK raises varied types
            logger.warning("Gemini provider failed: %s", exc)
            raise ProviderError(f"gemini: {exc}") from exc

        parts = response.candidates[0].content.parts
        text = "".join(p.text for p in parts if p.text)
        tool_calls = [
            ToolCall(
                id=p.function_call.name or "",
                name=p.function_call.name or "",
                arguments=dict(p.function_call.args or {}),
            )
            for p in parts
            if p.function_call
        ]
        return LLMResponse(content=text or None, tool_calls=tool_calls)
