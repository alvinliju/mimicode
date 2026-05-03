"""Tests for routing statistics tools."""
import json
import pytest
from pathlib import Path

from tools_router import analyze_routing, format_routing_stats


@pytest.fixture
def mock_session(tmp_path):
    """Create a mock session with routing events."""
    session_id = "test123"
    session_file = tmp_path / "sessions" / f"{session_id}.jsonl"
    session_file.parent.mkdir(exist_ok=True)
    
    events = [
        {"kind": "model_route", "data": {"step": 0, "model": "claude-sonnet-4-5-20250929", "reason": "first_turn", "has_guidance": False}},
        {"kind": "model_route", "data": {"step": 1, "model": "claude-3-5-haiku-20250312", "reason": "simple_edit", "has_guidance": True}},
        {"kind": "model_route", "data": {"step": 2, "model": "claude-3-5-haiku-20250312", "reason": "simple_read", "has_guidance": True}},
        {"kind": "model_route", "data": {"step": 3, "model": "claude-sonnet-4-5-20250929", "reason": "multi_file", "has_guidance": False}},
        {"kind": "other_event", "data": {"some": "data"}},  # Should be ignored
    ]
    
    with open(session_file, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    
    return session_file.parent.parent, session_id


def test_analyze_routing_nonexistent_session(tmp_path, monkeypatch):
    """Test analyzing a session that doesn't exist."""
    monkeypatch.setattr("tools_router.LOG_DIR", str(tmp_path / "sessions"))
    stats = analyze_routing("nonexistent")
    assert "error" in stats


def test_analyze_routing_with_data(mock_session, monkeypatch):
    """Test analyzing routing with actual data."""
    log_dir, session_id = mock_session
    monkeypatch.setattr("tools_router.LOG_DIR", str(log_dir / "sessions"))
    
    stats = analyze_routing(session_id)
    
    assert stats["total_routes"] == 4
    assert stats["haiku_pct"] == 50.0  # 2 out of 4
    assert "claude-sonnet-4-5-20250929" in stats["by_model"]
    assert "claude-3-5-haiku-20250312" in stats["by_model"]
    assert stats["by_model"]["claude-3-5-haiku-20250312"] == 2
    assert stats["by_model"]["claude-sonnet-4-5-20250929"] == 2
    assert stats["by_reason"]["simple_edit"] == 1
    assert stats["by_reason"]["simple_read"] == 1
    assert stats["by_reason"]["first_turn"] == 1
    assert stats["by_reason"]["multi_file"] == 1


def test_analyze_routing_empty_session(tmp_path, monkeypatch):
    """Test analyzing a session with no routing events."""
    monkeypatch.setattr("tools_router.LOG_DIR", str(tmp_path / "sessions"))
    session_id = "empty"
    session_file = tmp_path / "sessions" / f"{session_id}.jsonl"
    session_file.parent.mkdir(exist_ok=True)
    
    events = [
        {"kind": "user_message", "data": {"chars": 10}},
        {"kind": "tool_call", "data": {"name": "bash"}},
    ]
    
    with open(session_file, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    
    stats = analyze_routing(session_id)
    assert stats["total_routes"] == 0
    assert stats["haiku_pct"] == 0.0


def test_format_routing_stats_error():
    """Test formatting error stats."""
    stats = {"error": "Session not found"}
    result = format_routing_stats(stats)
    assert "Error: Session not found" in result


def test_format_routing_stats_no_data():
    """Test formatting when there's no routing data."""
    stats = {
        "total_routes": 0,
        "by_model": {},
        "by_reason": {},
        "haiku_pct": 0.0,
    }
    result = format_routing_stats(stats)
    assert "No routing data available" in result


def test_format_routing_stats_with_data():
    """Test formatting actual routing stats."""
    stats = {
        "total_routes": 10,
        "haiku_pct": 60.0,
        "by_model": {
            "claude-3-5-haiku-20250312": 6,
            "claude-sonnet-4-5-20250929": 4,
        },
        "by_reason": {
            "first_turn": 2,
            "simple_edit": 4,
            "simple_read": 2,
            "multi_file": 2,
        },
    }
    
    result = format_routing_stats(stats)
    
    assert "Total routing decisions: 10" in result
    assert "Haiku usage: 60.0%" in result
    assert "By model:" in result
    assert "By reason:" in result
    assert "simple_edit" in result
    assert "first_turn" in result
