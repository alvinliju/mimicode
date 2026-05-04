"""Session history tracking - remembers last 5 closed sessions for quick restoration."""
import json
import time
from pathlib import Path
from typing import TypedDict

SESSIONS_DIR = Path.home() / ".mimi" / "sessions"
HISTORY_FILE = SESSIONS_DIR / ".session_history.json"
MAX_HISTORY = 5


class SessionHistoryEntry(TypedDict):
    """A single session history entry."""
    session_id: str
    closed_at: float  # timestamp
    closed_at_str: str  # human readable


def load_history() -> list[SessionHistoryEntry]:
    """Load session history from disk."""
    if not HISTORY_FILE.exists():
        return []
    
    try:
        with HISTORY_FILE.open("r") as f:
            data = json.load(f)
            return data.get("history", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history: list[SessionHistoryEntry]) -> None:
    """Save session history to disk."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    with HISTORY_FILE.open("w") as f:
        json.dump({"history": history}, f, indent=2)


def add_to_history(session_id: str) -> None:
    """Add a session to the history when it's closed."""
    history = load_history()
    
    # Remove this session if it already exists in history
    history = [entry for entry in history if entry["session_id"] != session_id]
    
    # Add new entry at the beginning
    from datetime import datetime
    now = time.time()
    entry: SessionHistoryEntry = {
        "session_id": session_id,
        "closed_at": now,
        "closed_at_str": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
    }
    history.insert(0, entry)
    
    # Keep only the last MAX_HISTORY entries
    history = history[:MAX_HISTORY]
    
    save_history(history)


def get_most_recent() -> SessionHistoryEntry | None:
    """Get the most recently closed session."""
    history = load_history()
    return history[0] if history else None


def get_by_session_id(session_id: str) -> SessionHistoryEntry | None:
    """Find a session in history by ID."""
    history = load_history()
    for entry in history:
        if entry["session_id"] == session_id:
            return entry
    return None


def get_all() -> list[SessionHistoryEntry]:
    """Get all session history entries."""
    return load_history()
