"""tests for tools_session.py."""
import json
import pytest
from tools_session import session_stats


def test_session_stats(tmp_path):
    session_file = tmp_path / "test_session.jsonl"
    events = [
        {"t": 0.0, "session": "abc123", "kind": "start", "data": {}},
        {"t": 1.5, "session": "abc123", "kind": "tool_call", "data": {}},
        {"t": 2.3, "session": "abc123", "kind": "tool_call", "data": {}},
        {"t": 3.7, "session": "abc123", "kind": "end", "data": {}},
    ]
    session_file.write_text("\n".join(json.dumps(e) for e in events))
    stats = session_stats(session_file)
    assert stats["id"] == "abc123"
    assert stats["events"] == 4
    assert stats["by_kind"] == {"start": 1, "tool_call": 2, "end": 1}
    assert stats["duration_s"] == 3.7
