"""anthropic provider. one function: call_claude."""
from anthropic import AsyncAnthropic

from logger import log

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 8192


async def call_claude(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: AsyncAnthropic | None = None,
) -> dict:
    """one call to claude. returns the full assistant message dict.
    client is injectable for tests. no retries yet; surface errors."""
    client = client or AsyncAnthropic()
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools

    log("model_request", {"model": model, "n_messages": len(messages), "n_tools": len(tools or [])})
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
