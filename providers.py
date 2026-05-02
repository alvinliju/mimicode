"""anthropic provider. one function: call_claude.

Prompt caching: by default we mark three cache breakpoints (tools, system,
last message). Anthropic caches any identical prefix for 5 minutes, charging
10% of base input tokens on cache reads. See:
https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""
import asyncio
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


async def call_claude_streaming(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: AsyncAnthropic | None = None,
    cache: bool = True,
    on_event=None,
    cancel_event: asyncio.Event | None = None,
):
    """streaming version of call_claude. yields events as they arrive.
    on_event: optional async callback(event_type, data) for real-time updates."""
    client = client or AsyncAnthropic()
    kwargs: dict = {"model": model, "max_tokens": max_tokens}

    if system:
        kwargs["system"] = _wrap_system(system) if cache else system

    if tools:
        kwargs["tools"] = _cache_last_tool(tools) if cache else tools

    kwargs["messages"] = _cache_last_message(messages) if cache else messages

    log("model_request_streaming", {
        "model": model,
        "n_messages": len(messages),
        "n_tools": len(tools or []),
        "cache": cache,
    })

    content_blocks = []
    usage_data = {}

    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            if cancel_event and cancel_event.is_set():
                break
            await asyncio.sleep(0)
            
            event_type = event.type
            
            # Handle different event types
            if event_type == "content_block_start":
                idx = event.index
                block_type = event.content_block.type
                if block_type == "text":
                    content_blocks.append({"type": "text", "text": ""})
                    if on_event:
                        await on_event("text_start", {"index": idx})
                elif block_type == "tool_use":
                    block_data = {
                        "type": "tool_use",
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": {},
                    }
                    content_blocks.append(block_data)
                    if on_event:
                        await on_event("tool_start", {
                            "index": idx,
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                        })
            
            elif event_type == "content_block_delta":
                idx = event.index
                delta = event.delta
                if delta.type == "text_delta":
                    content_blocks[idx]["text"] += delta.text
                    if on_event:
                        await on_event("text_delta", {"index": idx, "text": delta.text})
                elif delta.type == "input_json_delta":
                    # Accumulate JSON input for tool_use
                    if "input_json" not in content_blocks[idx]:
                        content_blocks[idx]["input_json"] = ""
                    content_blocks[idx]["input_json"] += delta.partial_json
            
            elif event_type == "content_block_stop":
                idx = event.index
                # Finalize tool_use input by parsing accumulated JSON
                if content_blocks[idx]["type"] == "tool_use" and "input_json" in content_blocks[idx]:
                    import json
                    try:
                        content_blocks[idx]["input"] = json.loads(content_blocks[idx]["input_json"])
                        del content_blocks[idx]["input_json"]
                    except json.JSONDecodeError:
                        content_blocks[idx]["input"] = {}
                    
                    if on_event:
                        await on_event("tool_complete", {
                            "index": idx,
                            "id": content_blocks[idx]["id"],
                            "name": content_blocks[idx]["name"],
                            "input": content_blocks[idx]["input"],
                        })
            
            elif event_type == "message_delta":
                if hasattr(event, 'usage') and event.usage:
                    usage_data["tokens_out"] = getattr(event.usage, "output_tokens", 0)
            
            elif event_type == "message_stop":
                # Get final message from stream
                message = await stream.get_final_message()
                usage_data.update({
                    "tokens_in": message.usage.input_tokens,
                    "tokens_out": message.usage.output_tokens,
                    "cache_read": getattr(message.usage, "cache_read_input_tokens", 0) or 0,
                    "cache_write": getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
                })

    log("model_response_streaming", {
        "stop_reason": "end_turn",
        **usage_data,
    })

    return {
        "role": "assistant",
        "content": content_blocks,
    }
