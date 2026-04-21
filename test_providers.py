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


def test_call_claude_passes_system_and_tools():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(
        call_claude(
            [{"role": "user", "content": "x"}],
            system="you are terse",
            tools=[{"name": "bash", "description": "run", "input_schema": {}}],
            client=client,
        )
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "you are terse"
    assert kwargs["tools"][0]["name"] == "bash"
    assert "max_tokens" in kwargs
    assert kwargs["messages"][0]["content"] == "x"


def test_call_claude_omits_system_when_blank():
    client = _fake_client([{"type": "text", "text": "ok"}])
    run(call_claude([{"role": "user", "content": "x"}], client=client))
    kwargs = client.messages.create.call_args.kwargs
    assert "system" not in kwargs


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
