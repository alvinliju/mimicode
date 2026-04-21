"""mimicode: a minimal coding agent. the loop lives here."""
import asyncio
import os
import sys
from datetime import date

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


async def _dispatch(name: str, args: dict, cwd: str):
    fn = _TOOL_FNS.get(name)
    if fn is None:
        from tools import ToolResult
        return ToolResult(output=f"[error] unknown tool: {name}", is_error=True)
    log("tool_call", {"name": name, "args_keys": list(args.keys())})
    result = await fn(cwd=cwd, **args)
    log("tool_result", {"name": name, "is_error": result.is_error, "bytes": len(result.output)})
    return result


async def agent_turn(user_msg: str, cwd: str = ".", max_steps: int = 25) -> list[dict]:
    """run one user turn to completion. returns the full message list for this turn."""
    log("user_message", {"chars": len(user_msg)})
    messages: list[dict] = [{"role": "user", "content": user_msg}]
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


def _print_final(messages: list[dict]) -> None:
    last = messages[-1]
    if last["role"] != "assistant":
        return
    for block in last["content"]:
        if block.get("type") == "text":
            print(block["text"])


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python agent.py \"your prompt\"", file=sys.stderr)
        sys.exit(2)
    prompt = " ".join(sys.argv[1:])
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    sess = start_session()
    log("session_start", {"cwd": os.getcwd(), "prompt_chars": len(prompt)})
    print(f"[mimicode] session {sess.id} -> {sess.path}", file=sys.stderr)
    messages = asyncio.run(agent_turn(prompt, cwd=os.getcwd()))
    _print_final(messages)


if __name__ == "__main__":
    main()
