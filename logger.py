"""rlog: stupid simple JSONL session log. local only, no network.

A Session is an explicit object you can start/restart. The module keeps a
default session for convenience so `log(...)` just works. Each session writes
to sessions/<session_id>.jsonl.
"""
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

LOG_DIR = Path.home() / ".mimi" / "sessions"
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Session:
    id: str
    start: float
    path: Path

    @classmethod
    def new(cls, session_id: str | None = None, log_dir: Path = LOG_DIR) -> "Session":
        sid = session_id or uuid.uuid4().hex[:12]
        log_dir.mkdir(exist_ok=True)
        return cls(id=sid, start=time.time(), path=log_dir / f"{sid}.jsonl")

    def log(self, kind: str, data: dict | None = None) -> None:
        event = {
            "t": round(time.time() - self.start, 4),
            "session": self.id,
            "kind": kind,
            "data": data or {},
        }
        with self.path.open("a") as f:
            f.write(json.dumps(event) + "\n")


# default module-level session. agent.py may replace it via start_session().
_current: Session = Session.new()


def start_session(session_id: str | None = None) -> Session:
    """reset the module-level session. call this at the top of main()."""
    global _current
    _current = Session.new(session_id)
    _refresh_module_globals()
    return _current


def current_session() -> Session:
    return _current


def log(kind: str, data: dict | None = None) -> None:
    """append one JSONL event to the current session."""
    _current.log(kind, data)


def event_count(session_path: Path) -> int:
    """return the number of events in a session file."""
    return len(session_path.read_text().splitlines())


# back-compat: module-level names test_logger.py and older code import.
SESSION_ID = _current.id
SESSION_START = _current.start
LOG_PATH = _current.path


def _refresh_module_globals() -> None:
    """keep the back-compat globals pointed at the current session."""
    global SESSION_ID, SESSION_START, LOG_PATH
    SESSION_ID = _current.id
    SESSION_START = _current.start
    LOG_PATH = _current.path
