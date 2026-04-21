"""rlog: stupid simple JSONL session log. local only, no network."""
import json
import time
import uuid
from pathlib import Path

SESSION_ID = uuid.uuid4().hex[:12]
SESSION_START = time.time()
LOG_DIR = Path("sessions")
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"{SESSION_ID}.jsonl"


def log(kind: str, data: dict | None = None) -> None:
    """append one JSONL event to the current session's rlog."""
    event = {
        "t": round(time.time() - SESSION_START, 4),
        "session": SESSION_ID,
        "kind": kind,
        "data": data or {},
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(event) + "\n")
