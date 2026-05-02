"""tests for providers.py. unit tests use mocks; live tests require ANTHROPIC_API_KEY."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from providers import call_claude


def run(coro):
    return asyncio.run(coro)


def _fake_client(content_blocks, stop_reason="end_turn", tokens=(100, 50)):
    """build a mock AsyncAnthropic that returns a single response."""
    client = MagicMock()
    client.messages = MagicMock()
    resp = SimpleNamespace(
        content=[SimpleNamespace(model_dump=lambda b=b: b) for b in content_blocks],
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )
    client.messages.create = AsyncMock(return_value=resp)
    return client


def test_call_claude_returns_message_shape():
    client = _fake_client([{"type": "text", "text": "hi"}])
    msg = run(call_claude([{"role": "user", "content": "hello"}], client=client))
    assert msg["role"] == "assistant"
    assert msg["content"] == [{"type": "text", "text": "hi"}]


def test_call_claude_passes_system_and_tools_raw_when_cache_off():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(
        call_claude(
            [{"role": "user", "content": "x"}],
            system="you are terse",
            tools=[{"name": "bash", "description": "run", "input_schema": {}}],
            client=client,
            cache=False,
        )
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "you are terse"
    assert kwargs["tools"][0]["name"] == "bash"
    assert "cache_control" not in kwargs["tools"][0]
    assert "max_tokens" in kwargs
    assert kwargs["messages"][0]["content"] == "x"


def test_call_claude_omits_system_when_blank():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(call_claude([{"role": "user", "content": "x"}], client=client))
    kwargs = client.messages.create.call_args.kwargs
    assert "system" not in kwargs


def test_cache_wraps_system_as_block_with_cache_control():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(
        call_claude(
            [{"role": "user", "content": "hi"}],
            system="SYS",
            client=client,
            cache=True,
        )
    )
    sys_arg = client.messages.create.call_args.kwargs["system"]
    assert isinstance(sys_arg, list)
    assert sys_arg[0]["type"] == "text"
    assert sys_arg[0]["text"] == "SYS"
    assert sys_arg[0]["cache_control"] == {"type": "ephemeral"}


def test_cache_marks_last_tool_only():
    client = _fake_client([{"type": "text", "text": "ok"}])
    tools = [
        {"name": "a", "description": "A", "input_schema": {}},
        {"name": "b", "description": "B", "input_schema": {}},
        {"name": "c", "description": "C", "input_schema": {}},
    ]
    run(call_claude([{"role": "user", "content": "x"}], tools=tools, client=client, cache=True))
    sent = client.messages.create.call_args.kwargs["tools"]
    assert "cache_control" not in sent[0]
    assert "cache_control" not in sent[1]
    assert sent[2]["cache_control"] == {"type": "ephemeral"}


def test_cache_marks_last_message_promoting_string_to_block():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(call_claude([{"role": "user", "content": "hello"}], client=client, cache=True))
    msgs = client.messages.create.call_args.kwargs["messages"]
    content = msgs[-1]["content"]
    assert isinstance(content, list)
    assert content[-1]["text"] == "hello"
    assert content[-1]["cache_control"] == {"type": "ephemeral"}


def test_cache_marks_last_block_of_list_content():
    client = _fake_client([{"type": "text", "text": "ok"}])
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
                {"type": "tool_result", "tool_use_id": "t2", "content": "also done"},
            ],
        }
    ]
    run(call_claude(messages, client=client, cache=True))
    sent = client.messages.create.call_args.kwargs["messages"]
    content = sent[-1]["content"]
    assert "cache_control" not in content[0]
    assert content[-1]["cache_control"] == {"type": "ephemeral"}


def test_cache_does_not_mutate_caller_inputs():
    """caller passes messages/tools; we must not scribble on them."""
    client = _fake_client([{"type": "text", "text": "ok"}])
    tools = [{"name": "a", "description": "A", "input_schema": {}}]
    messages = [{"role": "user", "content": "x"}]
    run(call_claude(messages, tools=tools, client=client, cache=True))
    assert "cache_control" not in tools[0]
    assert messages[0]["content"] == "x"  # still a string


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live test; set ANTHROPIC_API_KEY to run",
)
def test_call_claude_live_smoke():
    msg = run(
        call_claude(
            [{"role": "user", "content": "Say the single word: pong"}],
            max_tokens=20,
        )
    )
    text = "".join(b.get("text", "") for b in msg["content"] if b.get("type") == "text")
    assert "pong" in text.lower()
