"""tools for analyzing session .jsonl files."""
import json
from pathlib import Path


def session_stats(session_path: Path) -> dict:
    """return stats from a session .jsonl file."""
    events = [json.loads(line) for line in session_path.read_text().splitlines() if line.strip()]
    by_kind = {}
    for event in events:
        by_kind[event["kind"]] = by_kind.get(event["kind"], 0) + 1
    return {
        "id": events[0]["session"] if events else "",
        "events": len(events),
        "by_kind": by_kind,
        "duration_s": events[-1]["t"] if events else 0.0,
    }
