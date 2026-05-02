"""mimicode: a minimal coding agent. the loop lives here.

CLI:
  python agent.py "your prompt"                 # new random session, one-shot
  python agent.py -s mysession "your prompt"    # named session (new or resume)
  python agent.py -s mysession                  # resume session in REPL
  python agent.py                               # new session in REPL
  python agent.py --tui                         # launch TUI mode
  python agent.py --tui -s mysession            # launch TUI with named session

Sessions persist to:
  sessions/<id>.jsonl          rlog event stream (metadata only)
  sessions/<id>.messages.json  full conversation (for resume)
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from logger import log, start_session
from providers import call_claude
from tools import bash, edit, read, write

SYSTEM_PROMPT = """You are a coding agent in a minimal harness called mimicode.
You have four tools: read, bash, edit, write. Use them deliberately.

SEARCH RULES (non-negotiable):
- Use `rg` (ripgrep) for every search. rg respects .gitignore by default.
- List files:          rg --files                  (not `find .` or `ls -R`)
- List by extension:   rg --files -t py            (not `find . -name '*.py'`)
- Search content:      rg 'pattern'                (not `grep -r`)
- Scope to a dir:      rg 'pattern' path/
- Case-insensitive:    rg -i 'pattern'
- With line numbers:   rg -n 'pattern'             (on by default for content search)
- List matching files: rg -l 'pattern'
Never run `find`, `grep -r`, `ls -R`, or `cat <codefile>`. Use the `read` tool for code files.

ALWAYS EXCLUDE from exploration: .venv/ .git/ node_modules/ sessions/ __pycache__/ dist/ build/ .pytest_cache/

EDITING RULES:
- `read` before `edit`. Always.
- `edit` requires old_text to match exactly once. Include 2-3 lines of surrounding context so the match is unique.
- `write` only for new files or full rewrites. Never for partial changes.

STYLE:
- Prefer one targeted tool call over a broad one. Scope searches.
- Tool output is capped at 100KB. If you hit that, your scope was too wide.
- Be concise. Cite file:line where relevant."""

TOOLS = [
    {
        "name": "bash",
        "description": (
            "Execute a shell command. Returns combined stdout+stderr, ANSI-stripped, "
            "tail-truncated at 100KB.\n\n"
            "SCOPING IS MANDATORY. A command that returns >50KB is almost always wrong — "
            "narrow it. Use `rg` for all search/listing. `find`, `grep -r`, `ls -R`, and "
            "`cat <codefile>` are BLOCKED by the harness and will return an error.\n\n"
            "Prefer: `rg --files`, `rg --files -t py`, `rg -l 'pat'`, `rg 'pat' path/`. "
            "Use the `read` tool (not `cat`) for code files.\n\n"
            "Respects .gitignore via rg. Never scans .venv/, .git/, node_modules/, sessions/."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "The shell command to run"},
                "timeout": {"type": "number", "description": "Optional seconds before killing the process"},
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "read",
        "description": "Read a text file. Returns line-numbered content. Defaults to first 2000 lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "description": "1-indexed starting line (default 1)"},
                "limit": {"type": "integer", "description": "max lines to return"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write",
        "description": "Create or overwrite a file. Creates parent directories.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit",
        "description": "Surgical find/replace. old_text must match exactly once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
]

_TOOL_FNS = {"bash": bash, "read": read, "write": write, "edit": edit}


def build_system(cwd: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nCurrent date: {date.today().isoformat()}\nCurrent working directory: {cwd}"


def messages_path(session_path: Path) -> Path:
    """sidecar file alongside the rlog that holds the full conversation."""
    return session_path.with_suffix(".messages.json")


def load_messages(session_path: Path) -> list[dict]:
    """load persisted messages for a session, or [] if none / corrupt."""
    mp = messages_path(session_path)
    if not mp.exists():
        return []
    try:
        data = json.loads(mp.read_text())
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        log("messages_load_error", {"path": str(mp)})
    return []


def save_messages(session_path: Path, messages: list[dict]) -> None:
    mp = messages_path(session_path)
    mp.write_text(json.dumps(messages, indent=2))


async def _dispatch(name: str, args: dict, cwd: str):
    fn = _TOOL_FNS.get(name)
    if fn is None:
        from tools import ToolResult
        return ToolResult(output=f"[error] unknown tool: {name}", is_error=True)
    log("tool_call", {"name": name, "args_keys": list(args.keys())})
    result = await fn(cwd=cwd, **args)
    # invariant: anthropic rejects tool_result with is_error=true and empty content.
    if result.is_error and not result.output:
        result.output = "[error] (no output)"
    log("tool_result", {"name": name, "is_error": result.is_error, "bytes": len(result.output)})
    return result


async def agent_turn(
    user_msg: str,
    messages: list[dict] | None = None,
    cwd: str = ".",
    max_steps: int = 25,
) -> list[dict]:
    """run one user turn to completion. appends user_msg to `messages` (or
    starts fresh if None) and returns the extended list. pass the same list
    back in next call to continue the conversation."""
    log("user_message", {"chars": len(user_msg), "resumed": bool(messages)})
    if messages is None:
        messages = []
    messages.append({"role": "user", "content": user_msg})
    system = build_system(cwd)
    for step in range(max_steps):
        assistant = await call_claude(messages, system=system, tools=TOOLS)
        messages.append(assistant)
        tool_uses = [b for b in assistant["content"] if b.get("type") == "tool_use"]
        if not tool_uses:
            log("turn_end", {"steps": step + 1, "reason": "no_tool_use"})
            return messages
        results = []
        for tu in tool_uses:
            result = await _dispatch(tu["name"], tu.get("input", {}) or {}, cwd)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result.output,
                    "is_error": result.is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    log("turn_end", {"steps": max_steps, "reason": "max_steps"})
    return messages


def _last_assistant_text(messages: list[dict]) -> str:
    """extract the final assistant text for printing."""
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        return "\n".join(
            b["text"] for b in msg["content"] if b.get("type") == "text"
        )
    return ""


def _print_final(messages: list[dict]) -> None:
    text = _last_assistant_text(messages)
    if text:
        print(text)


async def _run_one_shot(prompt: str, session_path: Path, cwd: str) -> None:
    messages = load_messages(session_path)
    resumed = bool(messages)
    if resumed:
        print(f"[mimicode] resumed {len(messages)} prior messages", file=sys.stderr)
    messages = await agent_turn(prompt, messages=messages, cwd=cwd)
    save_messages(session_path, messages)
    _print_final(messages)


async def _run_repl(session_path: Path, cwd: str) -> None:
    messages = load_messages(session_path)
    if messages:
        print(f"[mimicode] resumed {len(messages)} prior messages", file=sys.stderr)
    print("[mimicode] REPL. empty line or :q / ctrl-d to exit.", file=sys.stderr)
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break
        if not prompt or prompt in (":q", ":quit", ":exit"):
            break
        messages = await agent_turn(prompt, messages=messages, cwd=cwd)
        save_messages(session_path, messages)
        _print_final(messages)
        print()  # blank line between turns
    log("repl_end", {"turns": sum(1 for m in messages if m["role"] == "user")})


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agent", description="mimicode coding agent")
    p.add_argument("-s", "--session", metavar="ID", help="session id (new or resume)")
    p.add_argument("--tui", action="store_true", help="launch TUI (Text User Interface) mode")
    p.add_argument("prompt", nargs="*", help="prompt (omit for REPL)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Launch TUI mode if requested
    if args.tui:
        from tui import main as tui_main
        tui_main(session_id=args.session)
        return

    sess = start_session(args.session)
    prompt = " ".join(args.prompt).strip()
    log("session_start", {
        "cwd": os.getcwd(),
        "prompt_chars": len(prompt),
        "mode": "one_shot" if prompt else "repl",
        "requested_id": args.session,
    })
    print(f"[mimicode] session {sess.id} -> {sess.path}", file=sys.stderr)

    cwd = os.getcwd()
    if prompt:
        asyncio.run(_run_one_shot(prompt, sess.path, cwd))
    else:
        asyncio.run(_run_repl(sess.path, cwd))


if __name__ == "__main__":
    main()
