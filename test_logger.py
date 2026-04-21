"""tests for logger.py."""
import importlib
import json
import sys


def fresh_logger():
    """reload the module so we get a fresh SESSION_ID + empty log file."""
    for m in ("logger",):
        if m in sys.modules:
            del sys.modules[m]
    return importlib.import_module("logger")


def test_log_writes_jsonl():
    logger = fresh_logger()
    logger.log("test_event", {"x": 1})
    logger.log("another", {"y": [1, 2, 3]})

    lines = logger.LOG_PATH.read_text().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["kind"] == "test_event"
    assert first["data"] == {"x": 1}
    assert first["session"] == logger.SESSION_ID
    assert isinstance(first["t"], float)

    second = json.loads(lines[1])
    assert second["t"] >= first["t"], "timestamps must be monotonic"

    logger.LOG_PATH.unlink()


def test_log_with_no_data():
    logger = fresh_logger()
    logger.log("bare")
    lines = logger.LOG_PATH.read_text().splitlines()
    assert json.loads(lines[0])["data"] == {}
    logger.LOG_PATH.unlink()
