"""mimi_memory: structured JSON memory for mimicode sessions.

Layout:
  .mimi/memory/
    index.json                  lightweight global index
    sessions/<id>/
      meta.json                 session focus, open issues, recent changes
      refs.json                 component entry IDs this session touched
    components/<name>.json      per-component knowledge
    decisions/<slug>.json       architectural decisions
"""
import json
from datetime import date
from pathlib import Path

MEMORY_ROOT = Path(".mimi/memory")
INDEX_PATH = MEMORY_ROOT / "index.json"


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def _write_json(path: Path, data) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def load_index() -> list[dict]:
    return _read_json(INDEX_PATH, [])


def _upsert_index(entry_id: str, type_: str, file_rel: str, tags: list[str], summary: str) -> None:
    index = load_index()
    for entry in index:
        if entry["id"] == entry_id:
            entry.update({"type": type_, "file": file_rel, "tags": tags, "summary": summary})
            _write_json(INDEX_PATH, index)
            return
    index.append({"id": entry_id, "type": type_, "file": file_rel, "tags": tags, "summary": summary})
    _write_json(INDEX_PATH, index)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def write_component(
    name: str,
    summary: str,
    detail: str = "",
    related_files: list[str] | None = None,
    tags: list[str] | None = None,
    decisions: list[str] | None = None,
    changes: list[dict] | None = None,
) -> None:
    path = MEMORY_ROOT / "components" / f"{name}.json"
    existing = _read_json(path, {})
    today = date.today().isoformat()
    data = {
        "id": f"{name}-component",
        "type": "component",
        "created_at": existing.get("created_at", today),
        "updated_at": today,
        "related_files": related_files or existing.get("related_files", []),
        "tags": tags or existing.get("tags", []),
        "summary": summary,
        "detail": detail or existing.get("detail", ""),
        "decisions": decisions if decisions is not None else existing.get("decisions", []),
        "changes": changes if changes is not None else existing.get("changes", []),
    }
    _write_json(path, data)
    _upsert_index(
        entry_id=f"{name}-component",
        type_="component",
        file_rel=f"components/{name}.json",
        tags=data["tags"],
        summary=summary,
    )


def load_component(name: str) -> dict | None:
    path = MEMORY_ROOT / "components" / f"{name}.json"
    return _read_json(path, None)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def write_decision(slug: str, summary: str, detail: str = "", tags: list[str] | None = None) -> None:
    path = MEMORY_ROOT / "decisions" / f"{slug}.json"
    existing = _read_json(path, {})
    today = date.today().isoformat()
    data = {
        "id": slug,
        "type": "decision",
        "created_at": existing.get("created_at", today),
        "updated_at": today,
        "tags": tags or existing.get("tags", []),
        "summary": summary,
        "detail": detail or existing.get("detail", ""),
    }
    _write_json(path, data)
    _upsert_index(
        entry_id=slug,
        type_="decision",
        file_rel=f"decisions/{slug}.json",
        tags=data["tags"],
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _session_dir(session_id: str) -> Path:
    return MEMORY_ROOT / "sessions" / session_id


def load_session_meta(session_id: str) -> dict | None:
    return _read_json(_session_dir(session_id) / "meta.json", None)


def load_session_refs(session_id: str) -> list[str]:
    return _read_json(_session_dir(session_id) / "refs.json", [])


def update_session_meta(
    session_id: str,
    summary: str | None = None,
    focus_files: list[str] | None = None,
    open_issues: list[str] | None = None,
    recent_changes: list[dict] | None = None,
) -> None:
    path = _session_dir(session_id) / "meta.json"
    existing = _read_json(path, {})
    today = date.today().isoformat()
    data = {
        "id": session_id,
        "started": existing.get("started", today),
        "last_active": today,
        "focus_files": focus_files if focus_files is not None else existing.get("focus_files", []),
        "summary": summary if summary is not None else existing.get("summary", ""),
        "open_issues": open_issues if open_issues is not None else existing.get("open_issues", []),
        "recent_changes": recent_changes if recent_changes is not None else existing.get("recent_changes", []),
    }
    _write_json(path, data)


def add_session_ref(session_id: str, entry_id: str) -> None:
    path = _session_dir(session_id) / "refs.json"
    refs = _read_json(path, [])
    if entry_id not in refs:
        refs.append(entry_id)
        _write_json(path, refs)


# ---------------------------------------------------------------------------
# Context loader — called by agent at turn start
# ---------------------------------------------------------------------------

def load_session_context(session_id: str) -> str:
    """Return a compact context string to prepend to the system prompt."""
    meta = load_session_meta(session_id)
    if not meta:
        return ""

    refs = load_session_refs(session_id)
    lines = [
        "## Session memory",
        f"Session: {session_id}",
        f"Summary: {meta.get('summary', '')}",
    ]

    if meta.get("focus_files"):
        lines.append(f"Focus files: {', '.join(meta['focus_files'])}")

    if meta.get("open_issues"):
        lines.append("Open issues:")
        for issue in meta["open_issues"]:
            lines.append(f"  - {issue}")

    if meta.get("recent_changes"):
        lines.append("Recent changes:")
        for ch in meta["recent_changes"]:
            lines.append(f"  - {ch.get('file', '?')}: {ch.get('what', '')} ({ch.get('why', '')})")

    if refs:
        lines.append("Known components:")
        index = {e["id"]: e for e in load_index()}
        for ref in refs:
            entry = index.get(ref)
            if entry:
                lines.append(f"  - [{ref}] {entry.get('summary', '')}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Init — auto-create skeleton on first run
# ---------------------------------------------------------------------------

def init_memory(session_id: str) -> None:
    """Create .mimi/memory skeleton if it doesn't exist. Safe to call every run."""
    _ensure_dir(MEMORY_ROOT / "components")
    _ensure_dir(MEMORY_ROOT / "decisions")
    _ensure_dir(_session_dir(session_id))

    if not INDEX_PATH.exists():
        _write_json(INDEX_PATH, [])

    meta_path = _session_dir(session_id) / "meta.json"
    if not meta_path.exists():
        today = date.today().isoformat()
        _write_json(meta_path, {
            "id": session_id,
            "started": today,
            "last_active": today,
            "focus_files": [],
            "summary": "",
            "open_issues": [],
            "recent_changes": [],
        })

    refs_path = _session_dir(session_id) / "refs.json"
    if not refs_path.exists():
        _write_json(refs_path, [])


# ---------------------------------------------------------------------------
# Auto-update — called after each agent turn to track activity passively
# ---------------------------------------------------------------------------

def _extract_touched_files(messages: list[dict]) -> list[str]:
    """Scan ALL tool_use blocks across the conversation for explicit file paths."""
    seen: dict[str, None] = {}  # ordered set
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if block.get("type") == "tool_use":
                inp = block.get("input", {}) or {}
                path = inp.get("path") or inp.get("file")
                if path:
                    seen[path] = None
    return list(seen.keys())


def _extract_last_assistant_text(messages: list[dict]) -> str:
    """Return the last assistant plain-text response."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        parts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
        text = " ".join(parts).strip()
        if text:
            return text[:200]
    return ""


def _count_turns(messages: list[dict]) -> int:
    return sum(1 for m in messages if m.get("role") == "user"
               and isinstance(m.get("content"), str))


def auto_update_session(session_id: str, messages: list[dict]) -> None:
    """Passively update session meta after a turn — always writes last_active."""
    if not session_id:
        return

    meta = load_session_meta(session_id) or {}

    # merge touched files (most-recent first, capped at 20)
    touched = _extract_touched_files(messages)
    existing_files = meta.get("focus_files", [])
    merged_files = list(dict.fromkeys(touched + existing_files))[:20]

    # auto-populate summary from last assistant text when still blank
    summary = meta.get("summary") or _extract_last_assistant_text(messages)

    update_session_meta(
        session_id=session_id,
        focus_files=merged_files,
        summary=summary or meta.get("summary"),
    )


# ---------------------------------------------------------------------------
# memory_write tool handler — called when agent uses the memory_write tool
# ---------------------------------------------------------------------------

def handle_memory_write(session_id: str, args: dict) -> str:
    """Process a memory_write tool call from the agent. Returns confirmation string."""
    component = args.get("component", "").strip()
    summary = args.get("summary", "").strip()
    detail = args.get("detail", "")
    related_files = args.get("related_files", [])
    tags = args.get("tags", [])
    open_issues = args.get("open_issues", [])
    change_entry = args.get("change_entry")  # optional {file, what, why}

    if not component or not summary:
        return "[memory_write] error: component and summary are required"

    write_component(
        name=component,
        summary=summary,
        detail=detail,
        related_files=related_files,
        tags=tags,
    )
    add_session_ref(session_id, f"{component}-component")

    if change_entry or open_issues is not None:
        meta = load_session_meta(session_id) or {}
        existing_changes = meta.get("recent_changes", [])
        if change_entry:
            existing_changes = ([change_entry] + existing_changes)[:10]
        update_session_meta(
            session_id=session_id,
            open_issues=open_issues if open_issues else meta.get("open_issues", []),
            recent_changes=existing_changes,
            focus_files=related_files or meta.get("focus_files", []),
        )

    return f"[memory_write] saved component '{component}'"
