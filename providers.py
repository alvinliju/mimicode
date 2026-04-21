"""anthropic provider. one function: call_claude.

Prompt caching: by default we mark three cache breakpoints (tools, system,
last message). Anthropic caches any identical prefix for 5 minutes, charging
10% of base input tokens on cache reads. See:
https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""
from copy import deepcopy

from anthropic import AsyncAnthropic

from logger import log

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 8192
_CACHE = {"type": "ephemeral"}


def _wrap_system(system: str) -> list[dict]:
    """system must be a list of blocks to carry cache_control."""
    return [{"type": "text", "text": system, "cache_control": _CACHE}]


def _cache_last_tool(tools: list[dict]) -> list[dict]:
    """mark the last tool as a cache breakpoint; caches the entire tools block."""
    out = deepcopy(tools)
    out[-1]["cache_control"] = _CACHE
    return out


def _cache_last_message(messages: list[dict]) -> list[dict]:
    """mark the last content block of the last message as a cache breakpoint.
    caches the entire rolling conversation so far. promotes bare-string
    content to a text block since cache_control needs a block to attach to."""
    out = deepcopy(messages)
    last = out[-1]
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    content[-1]["cache_control"] = _CACHE
    last["content"] = content
    return out


async def call_claude(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: AsyncAnthropic | None = None,
    cache: bool = True,
) -> dict:
    """one call to claude. returns the full assistant message dict.
    client is injectable for tests. cache=True adds ephemeral breakpoints."""
    client = client or AsyncAnthropic()
    kwargs: dict = {"model": model, "max_tokens": max_tokens}

    if system:
        kwargs["system"] = _wrap_system(system) if cache else system

    if tools:
        kwargs["tools"] = _cache_last_tool(tools) if cache else tools

    kwargs["messages"] = _cache_last_message(messages) if cache else messages

    log("model_request", {
        "model": model,
        "n_messages": len(messages),
        "n_tools": len(tools or []),
        "cache": cache,
    })
    resp = await client.messages.create(**kwargs)
    msg = {
        "role": "assistant",
        "content": [block.model_dump() for block in resp.content],
    }
    log(
        "model_response",
        {
            "stop_reason": resp.stop_reason,
            "tokens_in": resp.usage.input_tokens,
            "tokens_out": resp.usage.output_tokens,
            "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        },
    )
    return msg
