"""tools for analyzing session .jsonl files."""
import json
from pathlib import Path

# Pricing per million tokens (claude-sonnet)
_PRICE = {
    "input":        3.00,
    "output":      15.00,
    "cache_read":   0.30,
    "cache_write":  3.75,
}


def session_stats(session_path: Path) -> dict:
    """return stats from a session .jsonl file."""
    events = [json.loads(line) for line in session_path.read_text().splitlines() if line.strip()]
    by_kind = {}
    for event in events:
        by_kind[event["kind"]] = by_kind.get(event["kind"], 0) + 1
    return {
        "id": events[0]["session"] if events else "",
        "events": len(events),
        "by_kind": by_kind,
        "duration_s": events[-1]["t"] if events else 0.0,
    }


def session_token_usage(session_path: Path) -> dict:
    """sum token counts from all model_response events in the session."""
    if not session_path.exists():
        return {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "cost_usd": 0.0}

    tokens_in = tokens_out = cache_read = cache_write = 0
    for line in session_path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("kind") == "model_response":
            d = event.get("data", {})
            tokens_in    += d.get("tokens_in", 0)
            tokens_out   += d.get("tokens_out", 0)
            cache_read   += d.get("cache_read", 0)
            cache_write  += d.get("cache_write", 0)

    cost = (
        tokens_in    / 1_000_000 * _PRICE["input"] +
        tokens_out   / 1_000_000 * _PRICE["output"] +
        cache_read   / 1_000_000 * _PRICE["cache_read"] +
        cache_write  / 1_000_000 * _PRICE["cache_write"]
    )
    return {
        "tokens_in":   tokens_in,
        "tokens_out":  tokens_out,
        "cache_read":  cache_read,
        "cache_write": cache_write,
        "cost_usd":    round(cost, 6),
    }
