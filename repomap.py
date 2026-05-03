"""repomap: a tiny static repo summary injected into the system prompt.

Goal: give the model the *shape* of the codebase before it makes any decisions,
so it stops doing scavenger-hunt reads to find well-known symbols.

Approach (deliberately minimal):
  - List Python files via `rg --files -t py` (respects .gitignore).
  - For each file, parse with ast and extract module-level Class / Function /
    AsyncFunction / UPPER_SNAKE constants. Methods listed under their class.
  - Render as a compact text block, capped at a token budget.
  - Cache to .mimi/repomap.txt so repeat agent invocations reuse the same
    string and Anthropic's prompt cache stays warm.

Non-goals:
  - No embeddings, no vector retrieval, no semantic ranking.
  - No multi-language support yet (Python only). Other languages render as
    bare filenames.
  - Not a source of truth — just a hint. Stale during a session is fine; the
    agent will read the actual file when it needs to act.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

CACHE_DIR = Path(".mimi")
CACHE_PATH = CACHE_DIR / "repomap.txt"

# rough chars-per-token for English+code; close enough for budgeting.
_CHARS_PER_TOKEN = 4
DEFAULT_TOKEN_BUDGET = 1500


def _list_files(cwd: Path) -> list[Path]:
    """Return repo files, gitignore-respecting, via rg. Falls back to rglob."""
    try:
        out = subprocess.run(
            ["rg", "--files", "--hidden", "--glob", "!.git/", "--glob", "!.mimi/"],
            cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return [cwd / line for line in out.stdout.splitlines() if line]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # fallback: pure-Python walk (slower, doesn't respect .gitignore)
    return [p for p in cwd.rglob("*") if p.is_file()]


def _format_args(args: ast.arguments) -> str:
    """Render an ast.arguments object into a short signature like 'a, b, *c, **d'."""
    parts: list[str] = []
    posonly = getattr(args, "posonlyargs", []) or []
    for a in posonly:
        parts.append(a.arg)
    if posonly:
        parts.append("/")
    for a in args.args:
        parts.append(a.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for a in args.kwonlyargs:
        parts.append(a.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def _extract_python(text: str) -> list[str]:
    """Return one-line strings describing each top-level symbol in a Python file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue
            prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
            out.append(f"  {prefix}{node.name}({_format_args(node.args)})")
        elif isinstance(node, ast.ClassDef):
            method_names: list[str] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("_") and sub.name not in {"__init__", "__call__"}:
                        continue
                    method_names.append(sub.name)
            base = f"  class {node.name}"
            if method_names:
                base += f" — {', '.join(method_names)}"
            out.append(base)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper() and not tgt.id.startswith("_"):
                    out.append(f"  {tgt.id}")
    return out


def _is_low_priority(rel: str) -> bool:
    """Tests and fixtures are useful but should yield budget to production code."""
    return (
        rel.startswith("tests/")
        or "/tests/" in rel
        or rel.startswith("bench/fixtures/")
        or rel.startswith("test_")
    )


def _build_text(cwd: Path) -> str:
    """Walk repo, extract symbols per file, render as a single text block.
    Production code is rendered first; tests/fixtures last so truncation
    drops them first when the budget is tight."""
    files = sorted(_list_files(cwd))
    py_files = [p for p in files if p.suffix == ".py"]
    other_files = [p for p in files if p.suffix != ".py" and p.is_file()]

    py_files.sort(key=lambda p: (_is_low_priority(p.relative_to(cwd).as_posix()), p.as_posix()))

    sections: list[str] = []
    for p in py_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        rel = p.relative_to(cwd).as_posix()
        # for low-priority files (tests/fixtures), summarize aggressively to save tokens
        if _is_low_priority(rel):
            symbols = _extract_python(text)
            if not symbols:
                continue
            sections.append(f"{rel}  ({len(symbols)} symbols)")
            continue
        symbols = _extract_python(text)
        if symbols:
            sections.append(f"{rel}\n" + "\n".join(symbols))
        else:
            sections.append(rel)

    body = "\n\n".join(sections)
    if other_files:
        listing = ", ".join(sorted({p.relative_to(cwd).as_posix() for p in other_files})[:50])
        body += f"\n\nOther files: {listing}"
    return body


def _truncate_to_budget(text: str, token_budget: int) -> str:
    """If text exceeds the token budget, truncate by section (file) until it fits."""
    if not text:
        return text
    max_chars = token_budget * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    sections = text.split("\n\n")
    kept: list[str] = []
    used = 0
    for s in sections:
        if used + len(s) + 2 > max_chars:
            break
        kept.append(s)
        used += len(s) + 2
    truncated = "\n\n".join(kept)
    omitted = len(sections) - len(kept)
    if omitted > 0:
        truncated += f"\n\n[... {omitted} more files omitted from repo-map]"
    return truncated


def build_repo_map(
    cwd: str | Path = ".",
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> str:
    """Return a token-budgeted text summary of the repo's Python structure.

    Caches to .mimi/repomap.txt under cwd. Pass force_refresh=True to rebuild.
    Returns "" on any failure — the agent should still work without a map.
    """
    cwd_path = Path(cwd).resolve()
    cache_file = cwd_path / CACHE_PATH

    if use_cache and not force_refresh and cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except OSError:
            pass

    try:
        text = _build_text(cwd_path)
    except Exception:
        return ""
    text = _truncate_to_budget(text, token_budget)

    if use_cache and text:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return text
