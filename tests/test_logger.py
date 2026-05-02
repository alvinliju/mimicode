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


def test_start_session_rotates_to_new_file():
    logger = fresh_logger()
    first_id = logger.SESSION_ID
    logger.log("from_first", {})
    first_path = logger.LOG_PATH

    logger.start_session()
    assert logger.SESSION_ID != first_id
    assert logger.LOG_PATH != first_path
    logger.log("from_second", {})

    assert first_path.read_text().count("from_first") == 1
    assert logger.LOG_PATH.read_text().count("from_second") == 1
    assert "from_second" not in first_path.read_text()

    first_path.unlink()
    logger.LOG_PATH.unlink()


def test_start_session_accepts_explicit_id():
    logger = fresh_logger()
    sess = logger.start_session("myrun123")
    assert sess.id == "myrun123"
    assert logger.SESSION_ID == "myrun123"
    assert logger.LOG_PATH.name == "myrun123.jsonl"
    logger.log("hello")
    assert "hello" in logger.LOG_PATH.read_text()
    logger.LOG_PATH.unlink()


def test_event_count():
    logger = fresh_logger()
    logger.log("first", {"a": 1})
    logger.log("second", {"b": 2})
    assert logger.event_count(logger.LOG_PATH) == 2
    logger.LOG_PATH.unlink()
