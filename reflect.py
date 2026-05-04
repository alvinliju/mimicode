"""reflect: post-session rule evolution.

Usage:
  python reflect.py <session_id>
  python reflect.py <session_id> --cwd /path/to/project
  python reflect.py <session_id> --dry-run

Reads the session transcript + current RULES.md + MEMORY.md, asks the model
for surgical edits to RULES.md, applies them, commits to git.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

GLOBAL_MIMI = Path.home() / ".mimi"
RULES_PATH = Path(".mimi/RULES.md")
MEMORY_PATH = Path(".mimi/MEMORY.md")
MODEL = "claude-haiku-4-5-20251001"
MAX_TRANSCRIPT_CHARS = 20_000  # tail of session to keep costs low

REFLECT_PROMPT = """\
You are reviewing a coding agent session to improve the agent's behavioral rules.

## Current RULES.md
{rules}

## Session memory (what the agent worked on)
{memory}

## Session transcript (most recent {chars} chars)
{transcript}

---
Identify where the agent made the wrong call, was corrected by the user, \
repeated a mistake, or took unnecessary steps.

Return the complete updated RULES.md with surgical changes only — \
strengthen existing rules, add new ones, remove ones that are resolved.
Rules must be short, specific, and actionable. No verbose explanations.
One rule per bullet. If no changes are needed return exactly: NO_CHANGE"""


def _load_env(root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    dotenv = root / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _flatten_transcript(messages: list[dict]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
        elif isinstance(content, list):
            for b in content:
                if b.get("type") == "text":
                    parts.append(f"[{role}] {b['text']}")
                elif b.get("type") == "tool_use":
                    inp = b.get("input", {}) or {}
                    parts.append(f"[tool:{b['name']}] {json.dumps(inp)[:200]}")
                elif b.get("type") == "tool_result":
                    out = (b.get("content") or "")[:300]
                    err = " (error)" if b.get("is_error") else ""
                    parts.append(f"[result{err}] {out}")
    return "\n".join(parts)


def reflect(session_id: str, cwd: Path, dry_run: bool = False) -> int:
    messages_path = GLOBAL_MIMI / "sessions" / f"{session_id}.messages.json"
    if not messages_path.exists():
        print(f"[reflect] no transcript found: {messages_path}", file=sys.stderr)
        return 1

    messages = json.loads(messages_path.read_text(encoding="utf-8"))
    transcript = _flatten_transcript(messages)
    transcript = transcript[-MAX_TRANSCRIPT_CHARS:]

    rules_path = cwd / RULES_PATH
    memory_path = cwd / MEMORY_PATH
    rules = rules_path.read_text(encoding="utf-8") if rules_path.exists() else "(empty)"
    memory = memory_path.read_text(encoding="utf-8") if memory_path.exists() else "(empty)"

    prompt = REFLECT_PROMPT.format(
        rules=rules,
        memory=memory,
        transcript=transcript,
        chars=MAX_TRANSCRIPT_CHARS,
    )

    env = {**os.environ, **_load_env(cwd)}
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[reflect] ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    result = resp.content[0].text.strip()
    # strip markdown code fences if model wrapped the output
    if result.startswith("```"):
        lines = result.splitlines()
        result = "\n".join(l for l in lines if not l.startswith("```")).strip()

    if result.startswith("NO_CHANGE"):
        print(f"[reflect] no rule changes for {session_id}")
        return 0

    if dry_run:
        print("[reflect] dry-run — proposed RULES.md:")
        print(result)
        return 0

    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(result + "\n", encoding="utf-8")
    print(f"[reflect] updated RULES.md ({len(result)} chars)")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("session_id")
    p.add_argument("--cwd", default=".")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    return reflect(args.session_id, Path(args.cwd).resolve(), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
