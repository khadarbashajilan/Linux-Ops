"""Agent loop tests with a scripted fake provider."""

import json

import pytest
from pydantic import BaseModel

from app.core.agent import LOOP_LIMIT_ANSWER, MAX_TOOL_ROUNDS, Agent
from app.llm.base import LLMResponse, ToolCall
from app.tools.registry import ToolRegistry
from tests.conftest import FakeProvider

pytestmark = pytest.mark.anyio


class AddArgs(BaseModel):
    """Arguments for the add test tool."""

    a: int
    b: int


def _tools() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool()
    async def add(args: AddArgs) -> dict[str, int]:
        """Add two integers."""
        return {"sum": args.a + args.b}

    return reg


def _call(name: str = "add", **arguments: object) -> ToolCall:
    return ToolCall(id="", name=name, arguments=arguments)


async def test_answer_without_tools() -> None:
    provider = FakeProvider([LLMResponse(content="hi")])
    result = await Agent(provider, _tools()).run("hello")
    assert result.answer == "hi"
    assert result.invoked_tools == []


async def test_tool_result_fed_back_with_dict_arguments() -> None:
    provider = FakeProvider([LLMResponse(tool_calls=[_call(a=2, b=3)]), LLMResponse(content="5")])
    result = await Agent(provider, _tools()).run("2+3?")

    assert result.answer == "5"
    assert result.invoked_tools == ["add"]
    _, assistant, tool = provider.calls[1]
    assert assistant["tool_calls"][0]["function"]["arguments"] == {"a": 2, "b": 3}
    assert tool["role"] == "tool"
    assert tool["tool_name"] == "add"
    assert json.loads(tool["content"]) == {"sum": 5}


async def test_parallel_calls_share_one_assistant_message() -> None:
    provider = FakeProvider(
        [LLMResponse(tool_calls=[_call(a=1, b=1), _call(a=2, b=2)]), LLMResponse(content="ok")]
    )
    await Agent(provider, _tools()).run("two sums")
    roles = [m["role"] for m in provider.calls[1]]
    assert roles == ["user", "assistant", "tool", "tool"]


async def test_tool_error_returned_to_model() -> None:
    provider = FakeProvider(
        [LLMResponse(tool_calls=[_call("missing")]), LLMResponse(content="sorry")]
    )
    result = await Agent(provider, _tools()).run("x")
    assert result.answer == "sorry"
    assert "unknown tool" in json.loads(provider.calls[1][-1]["content"])["error"]


async def test_loop_cap_returns_answer_instead_of_raising() -> None:
    provider = FakeProvider([LLMResponse(tool_calls=[_call(a=1, b=1)])] * MAX_TOOL_ROUNDS)
    result = await Agent(provider, _tools()).run("loop")
    assert result.answer == LOOP_LIMIT_ANSWER
    assert len(result.invoked_tools) == MAX_TOOL_ROUNDS
