"""compactor: in-session message compaction.

Shrinks the in-context messages list when it grows past a turn count or token
threshold by summarizing older user/assistant turns into a single synthetic
user message. The full transcript on disk (sessions/<id>.messages.json) is
left untouched. Compaction records are written to:

  sessions/<id>.compactions.jsonl       append-only structured records
  sessions/<id>.compactions.index.json  fast lookup index

Does NOT touch .mimi/MEMORY.md or .mimi/RULES.md. Those systems remain as-is.

Triggers (auto):
  - uncompacted user turns >= MIMICODE_COMPACT_TURN_INTERVAL (default 5)
  - last input tokens >= MIMICODE_COMPACT_TOKEN_THRESHOLD (default 20000)

Toggle:
  - MIMICODE_COMPACT_AUTO=0 disables auto-compaction (manual still works)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import anthropic

from logger import log

DEFAULT_TURN_INTERVAL = 5
DEFAULT_TOKEN_THRESHOLD = 20_000
KEEP_RECENT_USER_TURNS = 2
SUMMARIZER_MODEL = "claude-haiku-4-5-20251001"
SUMMARIZER_MAX_TOKENS = 2048

COMPACTION_PROMPT = """\
You are summarizing a slice of a coding-agent transcript so it can replace the original messages in-context.

Return ONLY a single JSON object — no prose, no code fences. Schema:
{{
  "one_line": "single sentence summary of this slice",
  "user_intents": ["..."],
  "decisions": ["..."],
  "files_touched": [{{"path": "...", "what": "...", "why": "..."}}],
  "tools_used": {{"bash": 0, "read": 0, "edit": 0, "write": 0}},
  "key_findings": ["..."],
  "open_issues": ["..."]
}}

If a previous "[COMPACTED ...]" marker appears in the slice, fold its contents
into your output rather than discarding it.

Slice transcript:
{transcript}
"""


def auto_enabled() -> bool:
    return os.environ.get("MIMICODE_COMPACT_AUTO", "1") not in ("0", "false", "False", "off")


def set_auto(value: bool) -> None:
    os.environ["MIMICODE_COMPACT_AUTO"] = "1" if value else "0"


def turn_interval() -> int:
    try:
        return max(1, int(os.environ.get("MIMICODE_COMPACT_TURN_INTERVAL", DEFAULT_TURN_INTERVAL)))
    except ValueError:
        return DEFAULT_TURN_INTERVAL


def token_threshold() -> int:
    try:
        return max(1000, int(os.environ.get("MIMICODE_COMPACT_TOKEN_THRESHOLD", DEFAULT_TOKEN_THRESHOLD)))
    except ValueError:
        return DEFAULT_TOKEN_THRESHOLD


# ---------------------------------------------------------------------------
# message inspection
# ---------------------------------------------------------------------------

def _is_real_user_turn(m: dict) -> bool:
    """A 'real' user turn: role=user with string content (not a tool_result list)."""
    return m.get("role") == "user" and isinstance(m.get("content"), str)


def _is_marker(m: dict) -> bool:
    return _is_real_user_turn(m) and m["content"].startswith("[COMPACTED")


def _user_turn_indices(messages: list[dict]) -> list[int]:
    return [i for i, m in enumerate(messages) if _is_real_user_turn(m)]


def find_compaction_split(messages: list[dict], keep_recent: int = KEEP_RECENT_USER_TURNS) -> int:
    """Index at which to split — everything < idx gets compacted.
    Returns 0 when there aren't enough user turns to compact safely.
    Splits on a user-turn boundary so tool_use/tool_result pairs stay intact.
    """
    user_indices = _user_turn_indices(messages)
    if len(user_indices) <= keep_recent:
        return 0
    return user_indices[-keep_recent]


def uncompacted_user_turn_count(messages: list[dict]) -> int:
    """Count real user turns excluding any compaction marker.
    Used to decide whether the turn-interval trigger should fire.
    """
    return sum(1 for m in messages if _is_real_user_turn(m) and not _is_marker(m))


def should_auto_compact(messages: list[dict], last_tokens_in: int) -> tuple[bool, str]:
    if not auto_enabled():
        return False, ""
    split = find_compaction_split(messages)
    if split == 0:
        return False, ""
    uncompacted = uncompacted_user_turn_count(messages)
    interval = turn_interval()
    if uncompacted >= interval + KEEP_RECENT_USER_TURNS:
        return True, f"turn_interval ({uncompacted} uncompacted turns)"
    threshold = token_threshold()
    if last_tokens_in and last_tokens_in >= threshold:
        return True, f"token_threshold ({last_tokens_in} >= {threshold})"
    return False, ""


# ---------------------------------------------------------------------------
# transcript flattening for the summarizer
# ---------------------------------------------------------------------------

def _flatten_for_summary(messages: list[dict], max_per_block: int = 600) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}] {content[:max_per_block]}")
        elif isinstance(content, list):
            for b in content:
                t = b.get("type")
                if t == "text":
                    parts.append(f"[{role}] {b.get('text', '')[:max_per_block]}")
                elif t == "tool_use":
                    inp = b.get("input", {}) or {}
                    parts.append(f"[tool:{b.get('name','?')}] {json.dumps(inp)[:300]}")
                elif t == "tool_result":
                    out = (b.get("content") or "")
                    if isinstance(out, list):
                        out = json.dumps(out)
                    err = " (error)" if b.get("is_error") else ""
                    parts.append(f"[result{err}] {str(out)[:max_per_block]}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# disk paths
# ---------------------------------------------------------------------------

def compactions_path(session_path: Path) -> Path:
    return session_path.with_suffix(".compactions.jsonl")


def index_path(session_path: Path) -> Path:
    return session_path.with_suffix(".compactions.index.json")


def _next_compaction_id(session_path: Path) -> str:
    p = compactions_path(session_path)
    if not p.exists():
        return "c001"
    n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    return f"c{n + 1:03d}"


def _append_record(session_path: Path, record: dict) -> None:
    p = compactions_path(session_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _update_index(session_path: Path, entry: dict) -> None:
    p = index_path(session_path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"compactions": []}
    else:
        data = {"compactions": []}
    data.setdefault("compactions", []).append(entry)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_compactions(session_path: Path) -> list[dict]:
    p = index_path(session_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("compactions", [])
    except (json.JSONDecodeError, OSError):
        return []


def load_compaction(session_path: Path, compaction_id: str) -> dict | None:
    p = compactions_path(session_path)
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("id") == compaction_id:
            return rec
    return None


# ---------------------------------------------------------------------------
# summarization
# ---------------------------------------------------------------------------

def _summarize(transcript: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"one_line": "compaction-skipped-no-api-key"}
    client = anthropic.Anthropic(api_key=api_key)
    prompt = COMPACTION_PROMPT.format(transcript=transcript)
    try:
        resp = client.messages.create(
            model=SUMMARIZER_MODEL,
            max_tokens=SUMMARIZER_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return {"one_line": f"compaction-summary-failed: {type(e).__name__}", "error": str(e)[:300]}

    text = resp.content[0].text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"one_line": "compaction-summary-parse-failed", "raw": text[:1500]}


def _format_marker(compaction_id: str, summary: dict, turn_range: tuple[int, int]) -> str:
    parts = [
        f"[COMPACTED — turns {turn_range[0]}–{turn_range[1]}, id={compaction_id}]",
        f"Summary: {summary.get('one_line', '(none)')}",
    ]
    if summary.get("user_intents"):
        parts.append("User intents: " + "; ".join(map(str, summary["user_intents"])))
    if summary.get("decisions"):
        parts.append("Decisions: " + "; ".join(map(str, summary["decisions"])))
    if summary.get("files_touched"):
        ft = ", ".join(
            f.get("path", "?") if isinstance(f, dict) else str(f)
            for f in summary["files_touched"]
        )
        parts.append(f"Files touched: {ft}")
    if summary.get("key_findings"):
        parts.append("Key findings: " + "; ".join(map(str, summary["key_findings"])))
    if summary.get("open_issues"):
        parts.append("Open issues: " + "; ".join(map(str, summary["open_issues"])))
    parts.append(
        f'(Full record available via recall_compaction(compaction_id="{compaction_id}").)'
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# main entry points
# ---------------------------------------------------------------------------

def compact(
    messages: list[dict],
    session_path: Path,
    keep_recent: int = KEEP_RECENT_USER_TURNS,
    reason: str = "manual",
) -> tuple[list[dict], dict | None]:
    """Compact older messages. Returns (new_messages, record_or_None).
    No-op (returns original list) when there's nothing safely compactable."""
    split = find_compaction_split(messages, keep_recent)
    if split == 0:
        return messages, None

    slice_to_compact = messages[:split]
    if not slice_to_compact:
        return messages, None

    user_indices_in_slice = [i for i, m in enumerate(slice_to_compact) if _is_real_user_turn(m)]
    if not user_indices_in_slice:
        return messages, None

    prior_turns = sum(
        (c.get("turn_range", [0, 0])[1] - c.get("turn_range", [0, 0])[0] + 1)
        for c in list_compactions(session_path)
    )
    real_in_slice = sum(1 for m in slice_to_compact if _is_real_user_turn(m) and not _is_marker(m))
    turn_lo = prior_turns + 1
    turn_hi = prior_turns + real_in_slice if real_in_slice else turn_lo

    transcript = _flatten_for_summary(slice_to_compact)
    summary = _summarize(transcript)
    cid = _next_compaction_id(session_path)
    timestamp = time.time()

    record = {
        "id": cid,
        "timestamp": timestamp,
        "turn_range": [turn_lo, turn_hi],
        "msg_count_compacted": len(slice_to_compact),
        "reason": reason,
        "summary": summary,
    }
    _append_record(session_path, record)
    _update_index(session_path, {
        "id": cid,
        "timestamp": timestamp,
        "turn_range": [turn_lo, turn_hi],
        "one_line": summary.get("one_line", ""),
        "reason": reason,
    })

    marker_text = _format_marker(cid, summary, (turn_lo, turn_hi))
    new_messages = (
        [
            {"role": "user", "content": marker_text},
            {"role": "assistant", "content": [
                {"type": "text", "text": f"Acknowledged compaction {cid}."}
            ]},
        ]
        + messages[split:]
    )

    log("compaction_done", {
        "id": cid,
        "reason": reason,
        "msgs_compacted": len(slice_to_compact),
        "turn_range": [turn_lo, turn_hi],
        "msgs_after": len(new_messages),
    })

    return new_messages, record


def maybe_compact(
    messages: list[dict],
    session_path: Path,
    last_tokens_in: int = 0,
) -> tuple[list[dict], dict | None]:
    """Auto-compact if a trigger fires. No-op otherwise."""
    fire, reason = should_auto_compact(messages, last_tokens_in)
    if not fire:
        return messages, None
    return compact(messages, session_path, reason=f"auto:{reason}")


def status_text(session_path: Path, last_tokens_in: int = 0) -> str:
    """Human-readable status for the :compact / /compact status command."""
    enabled = "on" if auto_enabled() else "off"
    interval = turn_interval()
    threshold = token_threshold()
    n = len(list_compactions(session_path))
    return (
        f"compaction: {enabled} · "
        f"every {interval} turns or {threshold} tokens · "
        f"last_tokens_in={last_tokens_in} · "
        f"prior compactions={n}"
    )
