"""tests for memory_search.py."""
from __future__ import annotations

import json
from pathlib import Path

from memory_search import (
    _escape_fts_query,
    _flatten_session,
    format_results,
    reindex,
    search,
    SearchResult,
)


def _seed_session(sessions_dir: Path, sid: str, messages: list) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{sid}.messages.json").write_text(json.dumps(messages))


def _seed_component(memory_root: Path, name: str, **fields) -> None:
    d = memory_root / "components"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"summary": "", "detail": "", "tags": [], **fields}))


def _seed_decision(memory_root: Path, slug: str, **fields) -> None:
    d = memory_root / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps({"summary": "", "detail": "", "tags": [], **fields}))


# ---------- low-level helpers ----------

def test_flatten_session_extracts_user_and_assistant_text():
    msgs = [
        {"role": "user", "content": "fix the markup crash"},
        {"role": "assistant", "content": [{"type": "text", "text": "I'll look at it"}]},
    ]
    text = _flatten_session(msgs)
    assert "fix the markup crash" in text
    assert "I'll look at it" in text


def test_flatten_session_extracts_tool_paths():
    msgs = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "edit", "input": {"path": "auth.py"}},
        ]},
    ]
    assert "auth.py" in _flatten_session(msgs)


def test_escape_fts_query_quotes_bare_words():
    out = _escape_fts_query("router model")
    assert '"router"' in out and '"model"' in out


def test_escape_fts_query_passes_through_explicit_phrases():
    assert _escape_fts_query('"intent based router"') == '"intent based router"'


def test_escape_fts_query_passes_through_operators():
    assert _escape_fts_query("router AND haiku") == "router AND haiku"


def test_escape_fts_query_strips_dangerous_punctuation():
    # a hyphen at start of token is an FTS NOT operator; we should defuse it
    out = _escape_fts_query("-foo")
    # the resulting string should not start with a bare hyphen-token
    assert out.startswith('"') or "-" not in out


# ---------- search end-to-end ----------

def test_search_finds_seeded_component(tmp_path):
    _seed_component(
        tmp_path / ".mimi/memory",
        "auth_layer",
        summary="Stateless JWT auth with rotating HMAC secret",
        related_files=["auth.py"],
        tags=["auth"],
    )
    results = search("JWT", cwd=tmp_path)
    assert len(results) >= 1
    assert any(r.source_id == "auth_layer" and r.kind == "component" for r in results)


def test_search_finds_seeded_decision(tmp_path):
    _seed_decision(
        tmp_path / ".mimi/memory",
        "use-jwt-stateless",
        summary="Adopted stateless JWT for auth",
    )
    results = search("stateless", cwd=tmp_path)
    assert any(r.source_id == "use-jwt-stateless" and r.kind == "decision" for r in results)


def test_search_finds_seeded_session(tmp_path):
    _seed_session(tmp_path / "sessions", "abc", [
        {"role": "user", "content": "let's refactor the markup handling in tui.py"},
        {"role": "assistant", "content": [{"type": "text", "text": "Found the issue, fixing now"}]},
    ])
    results = search("markup", cwd=tmp_path)
    assert any(r.source_id == "abc" and r.kind == "session" for r in results)


def test_search_filters_by_kind(tmp_path):
    _seed_component(tmp_path / ".mimi/memory", "auth_layer", summary="JWT auth", tags=["auth"])
    _seed_session(tmp_path / "sessions", "s1", [
        {"role": "user", "content": "JWT bug"},
    ])
    results = search("JWT", cwd=tmp_path, kind="component")
    assert all(r.kind == "component" for r in results)
    assert any(r.source_id == "auth_layer" for r in results)


def test_search_empty_query_returns_empty(tmp_path):
    _seed_component(tmp_path / ".mimi/memory", "x", summary="anything")
    assert search("", cwd=tmp_path) == []
    assert search("   ", cwd=tmp_path) == []


def test_search_no_data_returns_empty(tmp_path):
    assert search("anything", cwd=tmp_path) == []


def test_search_top_k_limits_results(tmp_path):
    for i in range(5):
        _seed_component(tmp_path / ".mimi/memory", f"comp_{i}", summary="auth thing")
    results = search("auth", top_k=2, cwd=tmp_path)
    assert len(results) <= 2


def test_search_returns_snippets(tmp_path):
    _seed_component(
        tmp_path / ".mimi/memory",
        "auth_layer",
        summary="Stateless JWT auth with rotating HMAC secret",
    )
    results = search("HMAC", cwd=tmp_path)
    assert results
    snippet = results[0].snippet.lower()
    assert "hmac" in snippet


def test_search_reindexes_after_new_data(tmp_path):
    _seed_component(tmp_path / ".mimi/memory", "auth_layer", summary="JWT auth")
    assert search("JWT", cwd=tmp_path)
    _seed_component(tmp_path / ".mimi/memory", "payments", summary="Stripe checkout flow")
    # reindex happens implicitly on each search() call
    results = search("Stripe", cwd=tmp_path)
    assert any(r.source_id == "payments" for r in results)


def test_search_handles_malformed_json(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "bad.messages.json").write_text("{not json")
    # should not raise; just skips the bad file
    results = search("anything", cwd=tmp_path)
    assert results == []


def test_format_results_no_matches_message():
    out = format_results([], "auth")
    assert "no matches" in out
    assert "auth" in out


def test_format_results_renders_each_result():
    results = [
        SearchResult(kind="component", source_id="auth_layer",
                     snippet="<<JWT>> auth with HMAC", rank=-1.0),
        SearchResult(kind="decision", source_id="use-jwt-stateless",
                     snippet="Adopted <<JWT>> for auth", rank=-0.8),
    ]
    out = format_results(results, "JWT")
    assert "auth_layer" in out and "use-jwt-stateless" in out
    assert "JWT" in out


def test_search_does_not_match_irrelevant_terms(tmp_path):
    _seed_component(tmp_path / ".mimi/memory", "auth_layer", summary="JWT auth with HMAC")
    _seed_component(tmp_path / ".mimi/memory", "payments", summary="Stripe checkout flow")
    results = search("Stripe", cwd=tmp_path)
    ids = [r.source_id for r in results]
    assert "payments" in ids
    assert "auth_layer" not in ids


# ---------- reindex helper ----------

def test_reindex_returns_counts(tmp_path):
    _seed_component(tmp_path / ".mimi/memory", "x", summary="anything")
    _seed_decision(tmp_path / ".mimi/memory", "d1", summary="some decision")
    _seed_session(tmp_path / "sessions", "s1", [{"role": "user", "content": "hi"}])
    counts = reindex(
        sessions_dir=tmp_path / "sessions",
        memory_root=tmp_path / ".mimi/memory",
        db_path=tmp_path / ".mimi/sessions.db",
    )
    assert counts == {"session": 1, "component": 1, "decision": 1}
