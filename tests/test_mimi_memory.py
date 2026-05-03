"""tests for mimi_memory.py."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# point MEMORY_ROOT at a temp dir for every test
@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    import mimi_memory
    monkeypatch.setattr(mimi_memory, "MEMORY_ROOT", tmp_path / ".mimi/memory")
    monkeypatch.setattr(mimi_memory, "INDEX_PATH", tmp_path / ".mimi/memory/index.json")
    # also fix the _session_dir closure reference
    monkeypatch.chdir(tmp_path)
    yield tmp_path


import mimi_memory as mm


# ---------------------------------------------------------------------------
# init_memory
# ---------------------------------------------------------------------------

def test_init_creates_skeleton():
    mm.init_memory("sesh1")
    assert (mm.MEMORY_ROOT / "components").is_dir()
    assert (mm.MEMORY_ROOT / "decisions").is_dir()
    assert (mm.MEMORY_ROOT / "sessions" / "sesh1").is_dir()
    assert mm.INDEX_PATH.exists()
    assert json.loads(mm.INDEX_PATH.read_text()) == []
    meta = json.loads((mm.MEMORY_ROOT / "sessions/sesh1/meta.json").read_text())
    assert meta["id"] == "sesh1"
    assert meta["summary"] == ""
    refs = json.loads((mm.MEMORY_ROOT / "sessions/sesh1/refs.json").read_text())
    assert refs == []


def test_init_is_idempotent():
    mm.init_memory("sesh1")
    (mm.MEMORY_ROOT / "sessions/sesh1/meta.json").write_text(
        json.dumps({"id": "sesh1", "started": "2026-01-01", "last_active": "2026-01-01",
                    "focus_files": ["x.py"], "summary": "existing", "open_issues": [], "recent_changes": []})
    )
    mm.init_memory("sesh1")  # should not overwrite
    meta = json.loads((mm.MEMORY_ROOT / "sessions/sesh1/meta.json").read_text())
    assert meta["summary"] == "existing"  # preserved


def test_init_different_sessions_isolated():
    mm.init_memory("a")
    mm.init_memory("b")
    assert (mm.MEMORY_ROOT / "sessions/a").is_dir()
    assert (mm.MEMORY_ROOT / "sessions/b").is_dir()


# ---------------------------------------------------------------------------
# write_component / load_component / index
# ---------------------------------------------------------------------------

def test_write_component_creates_file_and_index():
    mm.init_memory("s")
    mm.write_component("tui", "The TUI component", related_files=["tui.py"], tags=["ui"])
    comp = mm.load_component("tui")
    assert comp is not None
    assert comp["id"] == "tui-component"
    assert comp["summary"] == "The TUI component"
    assert comp["related_files"] == ["tui.py"]
    index = mm.load_index()
    assert any(e["id"] == "tui-component" for e in index)


def test_write_component_updates_existing():
    mm.init_memory("s")
    mm.write_component("tui", "v1")
    created_at = mm.load_component("tui")["created_at"]
    mm.write_component("tui", "v2")
    comp = mm.load_component("tui")
    assert comp["summary"] == "v2"
    assert comp["created_at"] == created_at  # preserved


def test_write_component_index_upserts_not_duplicates():
    mm.init_memory("s")
    mm.write_component("tui", "v1")
    mm.write_component("tui", "v2")
    index = mm.load_index()
    ids = [e["id"] for e in index]
    assert ids.count("tui-component") == 1


def test_load_component_missing_returns_none():
    mm.init_memory("s")
    assert mm.load_component("nonexistent") is None


# ---------------------------------------------------------------------------
# write_decision
# ---------------------------------------------------------------------------

def test_write_decision_appears_in_index():
    mm.init_memory("s")
    mm.write_decision("use-textual", "Chose Textual over curses", tags=["tui"])
    index = mm.load_index()
    entry = next(e for e in index if e["id"] == "use-textual")
    assert entry["type"] == "decision"
    assert entry["tags"] == ["tui"]


# ---------------------------------------------------------------------------
# session meta / refs
# ---------------------------------------------------------------------------

def test_update_session_meta_last_active_always_writes():
    mm.init_memory("s")
    mm.update_session_meta("s", summary="hello")
    meta = mm.load_session_meta("s")
    assert meta["summary"] == "hello"
    assert meta["last_active"] is not None


def test_update_session_meta_preserves_unset_fields():
    mm.init_memory("s")
    mm.update_session_meta("s", focus_files=["a.py"])
    mm.update_session_meta("s", summary="new summary")  # don't pass focus_files
    meta = mm.load_session_meta("s")
    assert meta["focus_files"] == ["a.py"]  # preserved
    assert meta["summary"] == "new summary"


def test_add_session_ref_no_duplicates():
    mm.init_memory("s")
    mm.add_session_ref("s", "tui-component")
    mm.add_session_ref("s", "tui-component")
    refs = mm.load_session_refs("s")
    assert refs.count("tui-component") == 1


# ---------------------------------------------------------------------------
# _extract_touched_files
# ---------------------------------------------------------------------------

def _make_messages(tool_calls: list[dict], final_text: str = "") -> list[dict]:
    msgs = [{"role": "user", "content": "do something"}]
    for tc in tool_calls:
        msgs.append({"role": "assistant", "content": [
            {"type": "tool_use", "name": tc["name"], "input": tc.get("input", {})}
        ]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "content": "ok"}]})
    msgs.append({"role": "assistant", "content": [{"type": "text", "text": final_text or "done"}]})
    return msgs


def test_extract_touched_files_from_read_edit_write():
    msgs = _make_messages([
        {"name": "read",  "input": {"path": "agent.py"}},
        {"name": "edit",  "input": {"path": "tui.py", "old_text": "x", "new_text": "y"}},
        {"name": "write", "input": {"path": "new_file.py", "content": ""}},
    ])
    files = mm._extract_touched_files(msgs)
    assert "agent.py" in files
    assert "tui.py" in files
    assert "new_file.py" in files


def test_extract_touched_files_bash_ignored():
    msgs = _make_messages([
        {"name": "bash", "input": {"cmd": "rg --files"}},
    ])
    files = mm._extract_touched_files(msgs)
    assert files == []


def test_extract_touched_files_no_duplicates():
    msgs = _make_messages([
        {"name": "read", "input": {"path": "agent.py"}},
        {"name": "edit", "input": {"path": "agent.py", "old_text": "x", "new_text": "y"}},
    ])
    files = mm._extract_touched_files(msgs)
    assert files.count("agent.py") == 1


def test_extract_touched_files_empty_messages():
    assert mm._extract_touched_files([]) == []


# ---------------------------------------------------------------------------
# auto_update_session
# ---------------------------------------------------------------------------

def test_auto_update_session_populates_focus_files_only():
    """Summary must NOT be auto-populated — only memory_write may set it."""
    mm.init_memory("s")
    msgs = _make_messages(
        [{"name": "edit", "input": {"path": "tui.py", "old_text": "a", "new_text": "b"}}],
        final_text="Fixed markup crash.",
    )
    mm.auto_update_session("s", msgs)
    meta = mm.load_session_meta("s")
    assert "tui.py" in meta["focus_files"]
    # critical: summary stays empty unless memory_write was called
    assert meta["summary"] == ""


def test_auto_update_session_does_not_overwrite_existing_summary():
    """If memory_write set a summary, auto_update must not touch it."""
    mm.init_memory("s")
    mm.update_session_meta("s", summary="Manual summary set by agent.")
    msgs = _make_messages([], final_text="Auto text.")
    mm.auto_update_session("s", msgs)
    meta = mm.load_session_meta("s")
    assert meta["summary"] == "Manual summary set by agent."


def test_auto_update_session_merges_files_across_turns():
    mm.init_memory("s")
    turn1 = _make_messages([{"name": "read", "input": {"path": "a.py"}}])
    mm.auto_update_session("s", turn1)
    turn2 = _make_messages([{"name": "edit", "input": {"path": "b.py", "old_text": "x", "new_text": "y"}}])
    mm.auto_update_session("s", turn2)
    meta = mm.load_session_meta("s")
    assert "a.py" in meta["focus_files"]
    assert "b.py" in meta["focus_files"]


def test_auto_update_session_no_session_id_is_noop():
    mm.init_memory("s")
    mm.auto_update_session("", [])  # should not raise


def test_auto_update_session_always_updates_last_active():
    mm.init_memory("s")
    mm.update_session_meta("s")
    before = mm.load_session_meta("s")["last_active"]
    mm.auto_update_session("s", [])
    after = mm.load_session_meta("s")["last_active"]
    assert after >= before  # monotonic


# ---------------------------------------------------------------------------
# load_session_context
# ---------------------------------------------------------------------------

def test_load_session_context_empty_when_no_meta():
    assert mm.load_session_context("ghost") == ""


def test_load_session_context_full_output():
    mm.init_memory("s")
    mm.write_component("tui", "The TUI widget layer", tags=["tui"])
    mm.add_session_ref("s", "tui-component")
    mm.update_session_meta("s",
        summary="Built TUI.",
        focus_files=["tui.py"],
        open_issues=["layout crash"],
        recent_changes=[{"file": "tui.py", "what": "markup=False", "why": "brackets crash Rich"}],
    )
    ctx = mm.load_session_context("s")
    assert "## Session memory" in ctx
    assert "Built TUI." in ctx
    assert "tui.py" in ctx
    assert "layout crash" in ctx
    assert "markup=False" in ctx
    assert "tui-component" in ctx


# ---------------------------------------------------------------------------
# handle_memory_write
# ---------------------------------------------------------------------------

def test_handle_memory_write_creates_component():
    mm.init_memory("s")
    result = mm.handle_memory_write("s", {
        "component": "logger",
        "summary": "JSONL event logger",
        "detail": "writes to sessions/<id>.jsonl",
        "related_files": ["logger.py"],
        "tags": ["logging"],
    })
    assert "logger" in result
    assert mm.load_component("logger") is not None
    assert "logger-component" in mm.load_session_refs("s")


def test_handle_memory_write_missing_required_fields():
    mm.init_memory("s")
    result = mm.handle_memory_write("s", {"component": "x"})  # no summary
    assert "error" in result


def test_handle_memory_write_records_change_entry():
    mm.init_memory("s")
    mm.handle_memory_write("s", {
        "component": "tui",
        "summary": "TUI layer",
        "change_entry": {"file": "tui.py", "what": "added markup=False", "why": "crash fix"},
        "open_issues": ["layout bug"],
    })
    meta = mm.load_session_meta("s")
    assert any(c["file"] == "tui.py" for c in meta["recent_changes"])
    assert "layout bug" in meta["open_issues"]
