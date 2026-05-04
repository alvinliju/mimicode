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
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent

from logger import log, start_session
from memory_search import format_results as _format_search_results
from memory_search import search as _memory_search
from mimi_memory import handle_memory_write, load_memory, load_rules
from providers import call_claude, call_claude_streaming
from repomap import build_repo_map
from router import augment_system_prompt, route_turn
from tools import ToolResult, bash, edit, read, write

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
- For multiple changes to the SAME file in one logical operation, prefer ONE `edit` call with
  `edits=[{old_text, new_text}, ...]` over multiple sequential `edit` calls. Batched edits are
  atomic: all succeed or none apply.
- `write` only for new files or full rewrites. Never for partial changes.

MEMORY RULES:
- After a turn that modified files OR made a meaningful decision, call `memory_write` with a one-sentence
  summary, the touched component name, and a `change_entry` describing what/why. The summary is NOT
  auto-generated — if you don't write one, the session has none.
- For purely read-only / exploratory turns that produced no carry-forward insight, skip memory_write.
- Do not write speculative or vague summaries. If you can't describe the change in one concrete sentence,
  the change probably wasn't significant enough to persist.
- When the user asks about something that may have been worked on before in this codebase
  ("how did we previously...", "have we built...", "where did we decide..."), call `memory_search`
  before reading source files. It searches past sessions, components, and decisions by keyword.

DEBUGGING RULES:
- Before editing any file in response to an error, determine whether the error is in the code or in how it was invoked. Most errors are invocation errors, not code bugs.
- `command not found: <file>.py` means the shell can't execute the file as a program — the script's code is almost certainly fine. ALWAYS explain `python <file>.py` as the fix. Do NOT edit the file, add a shebang, or chmod unless the user explicitly says they want the script runnable without a python prefix.
- Non-zero exit codes from test runners (pytest, etc.) are expected when tests fail — read the output for the actual counts. Do not treat a failing test run as a tool error.

STYLE:
- Prefer one targeted tool call over a broad one. Scope searches.
- Tool output is capped at 100KB. If you hit that, your scope was too wide.
- Be concise. Cite file:line where relevant.
- Do NOT create markdown (.md) files to summarize what is happening. Respond directly to the user."""

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
        "description": (
            "Find/replace on a single file. Two modes:\n"
            "  Single edit: pass old_text + new_text. old_text must match exactly once.\n"
            "  Batched edits: pass edits=[{old_text, new_text}, ...] to apply N changes "
            "atomically. Each edit's old_text must match exactly once in the file at the time "
            "it applies (earlier edits take effect first). If any edit fails, no changes land.\n"
            "Always read before editing. Include 2-3 lines of context in old_text so the match is unique. "
            "Prefer batched edits[] over multiple sequential edit calls on the same file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string", "description": "single-edit mode only"},
                "new_text": {"type": "string", "description": "single-edit mode only"},
                "edits": {
                    "type": "array",
                    "description": (
                        "batch mode: ordered list of {old_text, new_text} edits applied "
                        "sequentially to the file's in-memory buffer"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {"type": "string"},
                            "new_text": {"type": "string"},
                        },
                        "required": ["old_text", "new_text"],
                    },
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "memory_write",
        "description": (
            "Persist a structured note about what changed this turn so future sessions can pick up where this one left off. "
            "Call this when you have ANY of: completed a coherent task, modified one or more files, made an architectural decision, "
            "or surfaced an unresolved issue. The summary you write is the ONLY way the session gains a real summary — there is "
            "no auto-summarization. If you don't call it, future sessions resume blind. "
            "Pass:\n"
            "  - component: short name like 'tui', 'agent', 'logger', 'router', 'tools' (mandatory)\n"
            "  - summary: ONE sentence describing the current state of that component (mandatory)\n"
            "  - change_entry: {file, what, why} when files changed this turn\n"
            "  - open_issues: list of unresolved problems carried forward\n"
            "  - related_files: files this note covers\n"
            "Skip only when this turn was purely exploratory (read-only) and produced no insight worth carrying forward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {"type": "string", "description": "Component name (e.g. 'tui', 'agent')"},
                "summary": {"type": "string", "description": "One-line summary of the current state of this component"},
                "detail": {"type": "string", "description": "Full explanation of what was done and why"},
                "related_files": {"type": "array", "items": {"type": "string"}, "description": "File paths touched"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "open_issues": {"type": "array", "items": {"type": "string"}, "description": "Unresolved issues to carry forward"},
                "change_entry": {
                    "type": "object",
                    "description": "Record of the specific change made this turn",
                    "properties": {
                        "file": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                    },
                },
            },
            "required": ["component", "summary"],
        },
    },
    {
        "name": "memory_search",
        "description": (
            "Lexical (FTS5) search over past sessions, components, and decisions stored under "
            "~/.mimi/sessions/ and .mimi/. Use this BEFORE reading source files when the user "
            "asks about prior work in this codebase ('how did we previously...', 'have we built...', "
            "'where did we decide...'). Returns up to top_k snippets with source IDs. Local only — "
            "no embeddings, no network. You can read a returned session by calling `read` on "
            "~/.mimi/sessions/<source_id>.messages.json, or memory via .mimi/MEMORY.md.\n"
            "Query tips: bare keywords are auto-quoted (`router model` matches both words). "
            "Use double-quotes for an exact phrase: `\"intent based router\"`. Use `kind` to filter "
            "to one of session/component/decision when you know which you want."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "FTS5 query (keywords or phrases)"},
                "top_k": {"type": "integer", "description": "max results (default 5)"},
                "kind": {"type": "string", "description": "optional filter: 'session' | 'component' | 'decision'"},
            },
            "required": ["query"],
        },
    },
]


async def memory_search_tool(
    query: str,
    top_k: int = 5,
    kind: str | None = None,
    cwd: str = ".",
) -> ToolResult:
    """Tool wrapper around memory_search.search. Always succeeds; returns
    a no-match notice rather than an error when nothing is found.
    """
    try:
        results = _memory_search(query=query, top_k=top_k, kind=kind, cwd=cwd)
    except Exception as e:
        return ToolResult(output=f"[memory_search] error: {type(e).__name__}: {e}", is_error=True)
    return ToolResult(output=_format_search_results(results, query))


_TOOL_FNS = {
    "bash": bash,
    "read": read,
    "write": write,
    "edit": edit,
    "memory_search": memory_search_tool,
}


def build_system(cwd: str, repo_map: str = "") -> str:
    base = f"{SYSTEM_PROMPT}\n\nCurrent date: {date.today().isoformat()}\nCurrent working directory: {cwd}"
    if repo_map:
        base += (
            "\n\n## Repository map (Python symbols by file; not source of truth — read the file before editing)\n"
            f"{repo_map}"
        )
    rules = load_rules(cwd)
    if rules:
        base += f"\n\n## Behavioral rules\n{rules}"
    memory = load_memory(cwd)
    if memory:
        base += f"\n\n## Memory\n{memory}"
    return base


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


async def _dispatch(name: str, args: dict, cwd: str, session_id: str | None = None):
    from tools import ToolResult
    log("tool_call", {"name": name, "args_keys": list(args.keys())})
    if name == "memory_write":
        output = handle_memory_write(session_id or "", args)
        result = ToolResult(output=output, is_error=False)
    else:
        fn = _TOOL_FNS.get(name)
        if fn is None:
            result = ToolResult(output=f"[error] unknown tool: {name}", is_error=True)
        else:
            result = await fn(cwd=cwd, **args)
        if result.is_error and not result.output:
            result.output = "[error] (no output)"
    log("tool_result", {"name": name, "is_error": result.is_error, "bytes": len(result.output)})
    return result


class AgentInterrupted(Exception):
    """Raised when a cancel_event is set during agent_turn."""


async def agent_turn(
    user_msg: str,
    messages: list[dict] | None = None,
    cwd: str = ".",
    max_steps: int = 25,
    session_id: str | None = None,
    on_stream_event=None,
    cancel_event: asyncio.Event | None = None,
) -> list[dict]:
    """run one user turn to completion. returns extended messages list.
    Set cancel_event to interrupt mid-turn; raises AgentInterrupted.

    Env-var overrides (used by external benchmark harnesses):
      MIMICODE_MODEL       force a specific model id; bypasses route_turn.
      MIMICODE_MAX_STEPS   raise/lower the step budget (default 25). Useful
                           when running on terminal-bench where a single
                           task can need 50+ tool calls.
    """
    env_max = os.environ.get("MIMICODE_MAX_STEPS")
    if env_max:
        try:
            max_steps = max(1, int(env_max))
        except ValueError:
            pass
    log("user_message", {"chars": len(user_msg), "resumed": bool(messages)})
    if messages is None:
        messages = []
    messages.append({"role": "user", "content": user_msg})
    repo_map = build_repo_map(cwd) if cwd else ""
    system = build_system(cwd, repo_map)

    # pin model + guidance for the whole turn. mid-turn model flips invalidate
    # the prompt cache (each model has its own cache namespace) and per-step
    # guidance changes the cached system prefix — measured ~3x cost penalty.
    # decide once based on the user's original ask; let the same model see
    # the turn through.
    env_model = os.environ.get("MIMICODE_MODEL")
    if env_model:
        # external pinning (benchmark harnesses); skip routing entirely.
        from router import ModelChoice
        turn_choice = ModelChoice(model=env_model, reason="env_override")
    else:
        turn_choice = route_turn(user_msg)
    step_system = augment_system_prompt(system, turn_choice.guidance)
    log("model_route", {
        "step": "turn",
        "model": turn_choice.model,
        "reason": turn_choice.reason,
        "has_guidance": bool(turn_choice.guidance),
    })

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise AgentInterrupted

    for step in range(max_steps):
        _check_cancel()

        if on_stream_event:
            assistant = await call_claude_streaming(
                messages, system=step_system, tools=TOOLS,
                model=turn_choice.model,
                on_event=on_stream_event, cancel_event=cancel_event,
            )
        else:
            assistant = await call_claude(messages, system=step_system, tools=TOOLS, model=turn_choice.model)

        _check_cancel()

        messages.append(assistant)
        tool_uses = [b for b in assistant["content"] if b.get("type") == "tool_use"]
        if not tool_uses:
            log("turn_end", {"steps": step + 1, "reason": "no_tool_use"})
            return messages

        results = []
        for tu in tool_uses:
            _check_cancel()

            if on_stream_event:
                await on_stream_event("tool_exec_start", {
                    "name": tu["name"],
                    "args": tu.get("input", {}) or {},
                })

            try:
                result = await _dispatch(tu["name"], tu.get("input", {}) or {}, cwd, session_id)
            except Exception as e:
                result = ToolResult(output=f"[error] dispatch failed: {e}", is_error=True)

            _check_cancel()

            if on_stream_event:
                await on_stream_event("tool_exec_result", {
                    "name": tu["name"],
                    "output": result.output,
                    "is_error": result.is_error,
                })

            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result.output,
                "is_error": result.is_error,
            })

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


async def _run_one_shot(prompt: str, session_path: Path, cwd: str, session_id: str) -> None:
    messages = load_messages(session_path)
    resumed = bool(messages)
    if resumed:
        print(f"[mimicode] resumed {len(messages)} prior messages", file=sys.stderr)
    messages = await agent_turn(prompt, messages=messages, cwd=cwd, session_id=session_id)
    save_messages(session_path, messages)
    _print_final(messages)


async def _run_repl(session_path: Path, cwd: str, session_id: str) -> None:
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
        messages = await agent_turn(prompt, messages=messages, cwd=cwd, session_id=session_id)
        save_messages(session_path, messages)
        _print_final(messages)
        print()  # blank line between turns
    log("repl_end", {"turns": sum(1 for m in messages if m["role"] == "user")})


def _run_reflect(session_id: str, cwd: str) -> None:
    """Run reflect.py synchronously after a session ends. Fast (one haiku call)."""
    print(f"[mimicode] reflecting on session {session_id}...", file=sys.stderr)
    try:
        result = subprocess.run(
            [sys.executable, str(_AGENT_DIR / "reflect.py"), session_id, "--cwd", cwd],
            capture_output=True, text=True, timeout=60,
        )
        output = (result.stdout or result.stderr or "").strip()
        if output:
            print(output, file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[reflect] timed out", file=sys.stderr)
    except Exception as e:
        print(f"[reflect] skipped: {e}", file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agent", description="mimicode coding agent")
    p.add_argument("-s", "--session", metavar="ID", help="session id (new or resume)")
    p.add_argument("--tui", action="store_true", help="launch TUI (Text User Interface) mode")
    p.add_argument("prompt", nargs="*", help="prompt (omit for REPL)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    
    # Check for ripgrep (required dependency)
    if not shutil.which("rg"):
        print("error: ripgrep (rg) is not installed", file=sys.stderr)
        print("", file=sys.stderr)
        print("mimicode requires ripgrep for file searching.", file=sys.stderr)
        print("Install it with one of these methods:", file=sys.stderr)
        print("", file=sys.stderr)
        if sys.platform == "darwin":
            print("  macOS:  brew install ripgrep", file=sys.stderr)
        elif sys.platform.startswith("linux"):
            print("  Ubuntu/Debian:  sudo apt install ripgrep", file=sys.stderr)
            print("  Fedora/RHEL:    sudo dnf install ripgrep", file=sys.stderr)
            print("  Arch Linux:     sudo pacman -S ripgrep", file=sys.stderr)
        elif sys.platform == "win32":
            print("  Windows:  choco install ripgrep", file=sys.stderr)
            print("            scoop install ripgrep", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or download from: https://github.com/BurntSushi/ripgrep/releases", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run 'python3 check_deps.py' for a full dependency check.", file=sys.stderr)
        sys.exit(1)
    
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
        asyncio.run(_run_one_shot(prompt, sess.path, cwd, sess.id))
    else:
        asyncio.run(_run_repl(sess.path, cwd, sess.id))
    _run_reflect(sess.id, cwd)


if __name__ == "__main__":
    main()
