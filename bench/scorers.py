"""scorer helpers.

Scorers take a RunContext and return bool. Keep them small and literal.
Prefer clear names over clever abstractions.
"""
from __future__ import annotations

import filecmp
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunContext:
    """everything a scorer needs to make a pass/fail call."""
    cwd: Path                     # the tmpdir the agent ran in
    fixture: Path                 # the pristine fixture dir to diff against
    events: list[dict] = field(default_factory=list)   # rlog events
    messages: list[dict] = field(default_factory=list)  # full conversation
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def final_text(ctx: RunContext) -> str:
    """last assistant text turn."""
    for msg in reversed(ctx.messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, list):
            return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
    return ""


def bash_commands(ctx: RunContext) -> list[str]:
    """every bash command the agent asked the harness to run."""
    cmds: list[str] = []
    for msg in ctx.messages:
        if msg.get("role") != "assistant":
            continue
        for b in msg.get("content", []) or []:
            if b.get("type") == "tool_use" and b.get("name") == "bash":
                cmd = (b.get("input") or {}).get("cmd")
                if cmd:
                    cmds.append(cmd)
    return cmds


def any_bash_uses(ctx: RunContext, needles: list[str]) -> bool:
    """does any bash command contain any of these substrings?"""
    return any(any(n in c for n in needles) for c in bash_commands(ctx))


def cmd_blocked_count(ctx: RunContext) -> int:
    return sum(1 for e in ctx.events if e.get("kind") == "cmd_blocked")


def tool_uses(ctx: RunContext) -> dict[str, int]:
    """count of tool_use blocks in the conversation by tool name."""
    counts: dict[str, int] = {"bash": 0, "read": 0, "edit": 0, "write": 0}
    for msg in ctx.messages:
        if msg.get("role") != "assistant":
            continue
        for b in msg.get("content", []) or []:
            if b.get("type") == "tool_use":
                counts[b["name"]] = counts.get(b["name"], 0) + 1
    return counts


def file_text(cwd: Path, rel: str) -> str:
    p = cwd / rel
    return p.read_text() if p.exists() else ""


def file_contains(cwd: Path, rel: str, substring: str) -> bool:
    return substring in file_text(cwd, rel)


def modified_files(ctx: RunContext) -> set[str]:
    """files whose content differs from the fixture (or were added/removed)."""
    changed: set[str] = set()
    fixture = ctx.fixture
    cwd = ctx.cwd

    # everything present in fixture: changed if missing or different
    for fp in fixture.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(fixture).as_posix()
        target = cwd / rel
        if not target.exists():
            changed.add(rel)
        elif not filecmp.cmp(fp, target, shallow=False):
            changed.add(rel)

    # anything new in cwd that wasn't in fixture (ignoring sessions/ and caches)
    for fp in cwd.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(cwd).as_posix()
        if rel.startswith(("sessions/", ".pytest_cache/", "__pycache__/", ".mimi/")):
            continue
        if not (fixture / rel).exists():
            changed.add(rel)

    return changed


def only_modified(ctx: RunContext, allowed: list[str]) -> bool:
    """true if the set of changed files is a (non-strict) subset of allowed."""
    changed = modified_files(ctx)
    return changed.issubset(set(allowed))


# anthropic public pricing per Mtok, by model id (input, output, cached_read, cached_write).
# keep this literal so the cost number is auditable. unknown models fall back to
# Sonnet rates (conservative — over-reports rather than under-reports).
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5-20250929":  {"in": 3.0, "out": 15.0, "cr": 0.30, "cw": 3.75},
    "claude-haiku-4-5-20251001":   {"in": 1.0, "out":  5.0, "cr": 0.10, "cw": 1.25},
    "claude-opus-4-1-20250805":    {"in": 15.0, "out": 75.0, "cr": 1.50, "cw": 18.75},
}
_FALLBACK_RATES = PRICING["claude-sonnet-4-5-20250929"]


def _cost_for(usage: dict, rates: dict) -> float:
    return (
        usage["tokens_in"] * rates["in"]
        + usage["tokens_out"] * rates["out"]
        + usage["cache_read"] * rates["cr"]
        + usage["cache_write"] * rates["cw"]
    ) / 1_000_000


def metrics(ctx: RunContext) -> dict:
    """aggregate per-run stats from events.

    Cost is computed per-model: each model_response event carries the model
    that produced it, and we apply per-model rates. Older runs that didn't
    log model fall back to the most-recent model_request, then to Sonnet
    rates as a conservative final fallback.
    """
    m: dict = {
        "turns": 0,
        "steps": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cache_read": 0,
        "cache_write": 0,
        "bash": 0, "read": 0, "edit": 0, "write": 0,
        "memory_search": 0, "memory_write": 0,
        "tool_errors": 0,
        "cmd_blocked": 0,
    }
    by_model: dict[str, dict] = {}  # {model_id: {tokens_in, tokens_out, cache_read, cache_write}}
    last_request_model: str | None = None

    for e in ctx.events:
        k, d = e.get("kind"), e.get("data", {})
        if k == "user_message":
            m["turns"] += 1
        elif k == "model_request":
            m["steps"] += 1
            last_request_model = d.get("model") or last_request_model
        elif k in ("model_response", "model_response_streaming"):
            ti = d.get("tokens_in", 0) or 0
            to = d.get("tokens_out", 0) or 0
            cr = d.get("cache_read", 0) or 0
            cw = d.get("cache_write", 0) or 0
            m["tokens_in"] += ti
            m["tokens_out"] += to
            m["cache_read"] += cr
            m["cache_write"] += cw
            mname = d.get("model") or last_request_model or "unknown"
            slot = by_model.setdefault(
                mname, {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0}
            )
            slot["tokens_in"] += ti
            slot["tokens_out"] += to
            slot["cache_read"] += cr
            slot["cache_write"] += cw
        elif k == "tool_call":
            name = d.get("name")
            if name in m:
                m[name] += 1
        elif k == "tool_result":
            if d.get("is_error"):
                m["tool_errors"] += 1
        elif k == "cmd_blocked":
            m["cmd_blocked"] += 1

    cost_total = 0.0
    cost_by_model: dict[str, float] = {}
    for mname, usage in by_model.items():
        rates = PRICING.get(mname, _FALLBACK_RATES)
        c = _cost_for(usage, rates)
        cost_by_model[mname] = round(c, 5)
        cost_total += c
    m["cost_usd"] = round(cost_total, 5)
    m["cost_by_model"] = cost_by_model
    return m
