"""tests for agent.py. run: python3 test_agent.py"""
import json, importlib, sys
from pathlib import Path


def test_log_writes_jsonl():
    if "agent" in sys.modules:
        del sys.modules["agent"]
    agent = importlib.import_module("agent")

    agent.log("test_event", {"x": 1})
    agent.log("another", {"y": [1, 2, 3]})

    lines = agent.LOG_PATH.read_text().splitlines()
    assert len(lines) == 2, f"expected 2 lines, got {len(lines)}"

    first = json.loads(lines[0])
    assert first["kind"] == "test_event"
    assert first["data"] == {"x": 1}
    assert first["session"] == agent.SESSION_ID
    assert "t" in first and isinstance(first["t"], float)

    second = json.loads(lines[1])
    assert second["t"] >= first["t"], "timestamps must be monotonic"

    agent.LOG_PATH.unlink()
    print("ok: test_log_writes_jsonl")


if __name__ == "__main__":
    test_log_writes_jsonl()
