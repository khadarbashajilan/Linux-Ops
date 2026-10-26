"""Tool registry.

The ``@tool`` decorator registers an async function whose single argument is
a Pydantic model. JSON schemas for the LLM are generated from the model, so
tool definitions stay DRY. The ``risk`` tier is recorded now and enforced by
the safety layer in later phases.
"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.llm.base import ToolSchema

Risk = Literal["safe", "confirm", "block"]
ToolHandler = Callable[[Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolInfo:
    """Metadata for a registered tool."""

    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    risk: Risk

    def schema(self) -> ToolSchema:
        """Return this tool as a function schema for the model."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


class ToolRegistry:
    """Registry of all tools exposed to the LLM."""

    def __init__(self) -> None:
        """Initialise an empty tool map."""
        self._tools: dict[str, ToolInfo] = {}

    def register(self, tool_info: ToolInfo) -> None:
        """Register a tool by name, rejecting duplicates.

        Args:
            tool_info: the tool to register.

        Raises:
            ValueError: if a tool with the same name already exists.

        """
        if tool_info.name in self._tools:
            raise ValueError(f"tool already registered: {tool_info.name}")
        self._tools[tool_info.name] = tool_info

    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        risk: Risk = "safe",
    ) -> Callable[[ToolHandler], ToolHandler]:
        """Return a decorator that registers an async tool function.

        Args:
            name: tool name; defaults to the function name.
            description: shown to the LLM; defaults to the docstring.
            risk: safety tier (safe/confirm/block).

        Returns:
            A decorator that registers the function and returns it unchanged.

        Raises:
            TypeError: from the decorator, if the function does not take
                exactly one Pydantic model argument.

        """

        def decorator(func: ToolHandler) -> ToolHandler:
            params = list(inspect.signature(func).parameters.values())
            if len(params) != 1:
                raise TypeError(f"tool {func.__name__} must accept exactly one Pydantic arg")
            args_model = params[0].annotation
            if not (isinstance(args_model, type) and issubclass(args_model, BaseModel)):
                raise TypeError(f"tool {func.__name__} arg must be a Pydantic BaseModel")
            self.register(
                ToolInfo(
                    name=name or func.__name__,
                    description=description or inspect.getdoc(func) or "",
                    args_model=args_model,
                    handler=func,
                    risk=risk,
                )
            )
            return func

        return decorator

    def schemas(self) -> list[ToolSchema]:
        """Return all registered tools as function schemas."""
        return [info.schema() for info in self._tools.values()]

    def names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools)

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments and run a registered tool.

        Args:
            name: the tool name.
            arguments: raw arguments from the model.

        Returns:
            The tool's result dict.

        Raises:
            ValueError: if the tool is unknown.
            pydantic.ValidationError: if arguments fail the tool's model.

        """
        info = self._tools.get(name)
        if info is None:
            raise ValueError(f"unknown tool: {name}")
        return await info.handler(info.args_model.model_validate(arguments))


registry = ToolRegistry()
