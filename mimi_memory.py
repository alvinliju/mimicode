"""mimi_memory: flat markdown memory for mimicode sessions.

Layout:
  .mimi/MEMORY.md   structured component notes (agent-writable, upserted by component)
  .mimi/RULES.md    behavioral rules (reflect.py writes this, read-only for agent)
"""
from datetime import date
from pathlib import Path

MIMI_DIR = Path(".mimi")
MEMORY_PATH = MIMI_DIR / "MEMORY.md"
RULES_PATH = MIMI_DIR / "RULES.md"
MAX_MEMORY_LINES = 200


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError:
        return ""


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def load_memory(cwd: str = ".") -> str:
    return _read(Path(cwd) / MEMORY_PATH)


def load_rules(cwd: str = ".") -> str:
    return _read(Path(cwd) / RULES_PATH)


def _upsert_component(content: str, name: str, block: str) -> str:
    """Replace existing ## <name> section or append. Returns updated content."""
    header = f"## {name}"
    lines = content.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if start is None:
        sep = "\n" if content.strip() else ""
        return content + sep + block + "\n"
    # find end of this section (next ## or EOF)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[:start] + block.splitlines() + [""] + lines[end:])


def _cap(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= MAX_MEMORY_LINES:
        return text
    # drop oldest entries (top of file) to stay under cap
    return "\n".join(lines[-MAX_MEMORY_LINES:])


def handle_memory_write(session_id: str, args: dict, cwd: str = ".") -> str:
    component = args.get("component", "").strip()
    summary = args.get("summary", "").strip()
    if not component or not summary:
        return "[memory_write] error: component and summary are required"

    detail = args.get("detail", "").strip()
    files = args.get("related_files") or []
    tags = args.get("tags") or []
    change = args.get("change_entry")

    lines = [f"## {component} [{date.today().isoformat()}]"]
    lines.append(f"**summary:** {summary}")
    if files:
        lines.append(f"**files:** {', '.join(files)}")
    if tags:
        lines.append(f"**tags:** {', '.join(tags)}")
    if change:
        what = change.get("what", "")
        why = change.get("why", "")
        f = change.get("file", "")
        lines.append(f"**change:** {f} — {what} — {why}")
    if detail:
        lines.append(detail)

    block = "\n".join(lines)
    memory_path = Path(cwd) / MEMORY_PATH
    updated = _upsert_component(_read(memory_path), component, block)
    _write(memory_path, _cap(updated))
    return f"[memory_write] saved component '{component}'"
