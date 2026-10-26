"""Tool registry tests: registration rules, schema generation, execution."""

import pytest
from pydantic import BaseModel, ValidationError

from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.anyio


class EchoArgs(BaseModel):
    """Arguments for the echo test tool."""

    text: str


def _registry_with_echo() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool(risk="safe")
    async def echo(args: EchoArgs) -> dict[str, str]:
        """Echo the text back."""
        return {"text": args.text}

    return reg


def test_schema_generated_from_model() -> None:
    (schema,) = _registry_with_echo().schemas()
    assert schema["function"]["name"] == "echo"
    assert schema["function"]["description"] == "Echo the text back."
    assert schema["function"]["parameters"]["required"] == ["text"]


def test_duplicate_name_rejected() -> None:
    reg = _registry_with_echo()
    with pytest.raises(ValueError, match="already registered"):

        @reg.tool(name="echo")
        async def other(args: EchoArgs) -> dict[str, str]:
            return {}


def test_requires_single_pydantic_arg() -> None:
    reg = ToolRegistry()
    with pytest.raises(TypeError, match="exactly one"):

        @reg.tool()
        async def two(a: EchoArgs, b: EchoArgs) -> dict[str, str]:
            return {}

    with pytest.raises(TypeError, match="BaseModel"):

        @reg.tool()
        async def plain(a: str) -> dict[str, str]:
            return {}


async def test_execute_validates_arguments() -> None:
    reg = _registry_with_echo()
    assert await reg.execute("echo", {"text": "hi"}) == {"text": "hi"}
    with pytest.raises(ValidationError):
        await reg.execute("echo", {"text": 123})


async def test_unknown_tool() -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        await ToolRegistry().execute("nope", {})
