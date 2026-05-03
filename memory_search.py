"""memory_search: FTS5 lexical search over past sessions, components, decisions.

Local-only. Stdlib sqlite3. No vectors, no embeddings, no telemetry.

Storage:
  .mimi/sessions.db   SQLite FTS5 index, lazily rebuilt from source files

What gets indexed:
  - sessions/<id>.messages.json   user prompts + assistant text + tool paths
  - .mimi/memory/components/*.json  summary + detail + tags
  - .mimi/memory/decisions/*.json   summary + detail

Why not store vectors? Lexical search wins for our content (function names,
file paths, error messages, tags) because queries and documents share
vocabulary. Adding a vector layer is reserved for cases where bench results
prove lexical retrieval is missing semantically-similar things.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = ".mimi/sessions.db"
DEFAULT_SESSIONS_DIR = "sessions"
DEFAULT_MEMORY_ROOT = ".mimi/memory"


@dataclass
class SearchResult:
    kind: str            # 'session' | 'component' | 'decision'
    source_id: str
    snippet: str
    rank: float

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_id": self.source_id,
            "snippet": self.snippet,
            "rank": self.rank,
        }


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory USING fts5(
            kind UNINDEXED,
            source_id UNINDEXED,
            text,
            file_scope,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    return conn


def _flatten_session(messages: list) -> str:
    """Extract searchable text from a messages.json: user prompts, assistant
    text, and explicit file paths from tool_use calls."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
        elif isinstance(content, list):
            for b in content:
                btype = b.get("type")
                if btype == "text" and b.get("text"):
                    parts.append(f"[{role}] {b['text']}")
                elif btype == "tool_use":
                    inp = b.get("input", {}) or {}
                    path = inp.get("path") or inp.get("file") or ""
                    name = b.get("name", "?")
                    if path:
                        parts.append(f"[tool] {name} {path}")
    return "\n".join(parts)


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _index_sessions(conn: sqlite3.Connection, sessions_dir: Path) -> int:
    """Index all messages.json files. Returns count indexed."""
    if not sessions_dir.is_dir():
        return 0
    count = 0
    for mj in sessions_dir.glob("*.messages.json"):
        data = _read_json(mj)
        if not isinstance(data, list):
            continue
        sid = mj.stem.replace(".messages", "")
        text = _flatten_session(data)
        if not text.strip():
            continue
        # collect distinct file paths from tool_use calls for file_scope
        paths: list[str] = []
        for m in data:
            content = m.get("content") if isinstance(m, dict) else None
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_use":
                        p = (b.get("input") or {}).get("path")
                        if p and p not in paths:
                            paths.append(p)
        conn.execute(
            "INSERT INTO memory(kind, source_id, text, file_scope) VALUES(?,?,?,?)",
            ("session", sid, text, " ".join(paths)),
        )
        count += 1
    return count


def _index_components(conn: sqlite3.Connection, components_dir: Path) -> int:
    if not components_dir.is_dir():
        return 0
    count = 0
    for cj in components_dir.glob("*.json"):
        data = _read_json(cj)
        if not isinstance(data, dict):
            continue
        text_parts = [
            data.get("summary", ""),
            data.get("detail", ""),
            " ".join(data.get("tags", []) or []),
        ]
        text = "\n".join(p for p in text_parts if p)
        if not text.strip():
            continue
        file_scope = " ".join(data.get("related_files", []) or [])
        conn.execute(
            "INSERT INTO memory(kind, source_id, text, file_scope) VALUES(?,?,?,?)",
            ("component", cj.stem, text, file_scope),
        )
        count += 1
    return count


def _index_decisions(conn: sqlite3.Connection, decisions_dir: Path) -> int:
    if not decisions_dir.is_dir():
        return 0
    count = 0
    for dj in decisions_dir.glob("*.json"):
        data = _read_json(dj)
        if not isinstance(data, dict):
            continue
        text_parts = [
            data.get("summary", ""),
            data.get("detail", ""),
            " ".join(data.get("tags", []) or []),
        ]
        text = "\n".join(p for p in text_parts if p)
        if not text.strip():
            continue
        conn.execute(
            "INSERT INTO memory(kind, source_id, text, file_scope) VALUES(?,?,?,?)",
            ("decision", dj.stem, text, ""),
        )
        count += 1
    return count


def reindex(
    sessions_dir: Path,
    memory_root: Path,
    db_path: Path,
) -> dict:
    """Rebuild the FTS index from scratch. Returns counts per kind.
    Cheap on small repos (< few hundred docs); we'll add incremental
    indexing only if the bench shows latency matters."""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM memory")
        sessions = _index_sessions(conn, sessions_dir)
        components = _index_components(conn, memory_root / "components")
        decisions = _index_decisions(conn, memory_root / "decisions")
        conn.commit()
    finally:
        conn.close()
    return {"session": sessions, "component": components, "decision": decisions}


def _escape_fts_query(query: str) -> str:
    """FTS5 treats some chars as operators. For free-text queries we wrap
    bare words in quotes to avoid syntax errors; phrases stay intact."""
    q = query.strip()
    if not q:
        return q
    # if the user used FTS operators / quotes / parens, trust them
    if any(c in q for c in '"()'):
        return q
    if any(op in q.split() for op in ("AND", "OR", "NOT", "NEAR")):
        return q
    # default: split on whitespace and quote each token to neutralize -, : etc.
    tokens = q.split()
    safe = []
    for t in tokens:
        # strip punctuation that would otherwise be treated as operators
        cleaned = t.replace('"', "").strip()
        if cleaned:
            safe.append(f'"{cleaned}"')
    return " ".join(safe)


def search(
    query: str,
    top_k: int = 5,
    kind: str | None = None,
    cwd: str | Path = ".",
) -> list[SearchResult]:
    """Lexical search across sessions, components, and decisions.

    Always rebuilds the FTS index before searching. This is fast enough for
    typical session counts; we'll switch to incremental indexing if needed.

    Returns up to top_k SearchResult objects, ordered by FTS rank (best first).
    """
    if not query or not query.strip():
        return []
    cwd_p = Path(cwd).resolve()
    db_path = cwd_p / DEFAULT_DB
    sessions_dir = cwd_p / DEFAULT_SESSIONS_DIR
    memory_root = cwd_p / DEFAULT_MEMORY_ROOT

    reindex(sessions_dir, memory_root, db_path)

    conn = _connect(db_path)
    try:
        sql = (
            "SELECT kind, source_id, "
            "       snippet(memory, 2, '<<', '>>', '…', 16) AS snip, "
            "       rank "
            "FROM memory WHERE memory MATCH ?"
        )
        args: list = [_escape_fts_query(query)]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY rank LIMIT ?"
        args.append(top_k)
        try:
            rows = conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            # malformed FTS expression — return nothing rather than crashing
            return []
    finally:
        conn.close()

    return [
        SearchResult(kind=r[0], source_id=r[1], snippet=r[2] or "", rank=r[3])
        for r in rows
    ]


def format_results(results: list[SearchResult], query: str) -> str:
    """Render search results as a model-readable text block."""
    if not results:
        return f"[memory_search] no matches for: {query}"
    lines = [f"[memory_search] {len(results)} match(es) for: {query}"]
    for r in results:
        lines.append(f"\n--- {r.kind}: {r.source_id} ---")
        lines.append(r.snippet.strip() or "(no snippet)")
    return "\n".join(lines)
