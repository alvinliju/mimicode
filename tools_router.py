"""Router statistics and visualization tools."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from logger import LOG_DIR


def analyze_routing(session_id: str) -> dict:
    """
    Analyze model routing decisions for a session.
    
    Returns dict with:
      - total_routes: int
      - by_model: Counter of model choices
      - by_reason: Counter of routing reasons
      - haiku_pct: percentage using Haiku
      - cost_estimate: rough cost comparison
    """
    session_path = Path(LOG_DIR) / f"{session_id}.jsonl"
    if not session_path.exists():
        return {"error": "Session not found"}
    
    routes = []
    with open(session_path) as f:
        for line in f:
            event = json.loads(line)
            if event.get("kind") == "model_route":
                routes.append(event["data"])
    
    if not routes:
        return {
            "total_routes": 0,
            "by_model": {},
            "by_reason": {},
            "haiku_pct": 0.0,
        }
    
    by_model = Counter(r["model"] for r in routes)
    by_reason = Counter(r["reason"] for r in routes)
    
    total = len(routes)
    haiku_count = sum(1 for r in routes if "haiku" in r["model"].lower())
    haiku_pct = (haiku_count / total * 100) if total > 0 else 0
    
    return {
        "total_routes": total,
        "by_model": dict(by_model),
        "by_reason": dict(by_reason),
        "haiku_pct": round(haiku_pct, 1),
    }


def all_sessions_routing() -> dict:
    """
    Aggregate routing stats across all sessions.
    """
    log_dir = Path(LOG_DIR)
    if not log_dir.exists():
        return {"error": "No sessions found"}
    
    total_routes = 0
    by_model = Counter()
    by_reason = Counter()
    
    for session_path in log_dir.glob("*.jsonl"):
        with open(session_path) as f:
            for line in f:
                event = json.loads(line)
                if event.get("kind") == "model_route":
                    data = event["data"]
                    total_routes += 1
                    by_model[data["model"]] += 1
                    by_reason[data["reason"]] += 1
    
    if total_routes == 0:
        return {
            "total_routes": 0,
            "by_model": {},
            "by_reason": {},
            "haiku_pct": 0.0,
        }
    
    haiku_count = sum(count for model, count in by_model.items() if "haiku" in model.lower())
    haiku_pct = (haiku_count / total_routes * 100) if total_routes > 0 else 0
    
    return {
        "total_routes": total_routes,
        "by_model": dict(by_model),
        "by_reason": dict(by_reason),
        "haiku_pct": round(haiku_pct, 1),
    }


def format_routing_stats(stats: dict) -> str:
    """
    Pretty-print routing statistics.
    """
    if "error" in stats:
        return f"Error: {stats['error']}"
    
    if stats["total_routes"] == 0:
        return "No routing data available"
    
    lines = [
        f"Total routing decisions: {stats['total_routes']}",
        f"Haiku usage: {stats['haiku_pct']}%",
        "",
        "By model:",
    ]
    
    for model, count in stats["by_model"].items():
        pct = count / stats["total_routes"] * 100
        model_short = model.split("-")[-1] if "-" in model else model
        lines.append(f"  {model_short:10} {count:3} ({pct:5.1f}%)")
    
    lines.append("")
    lines.append("By reason:")
    for reason, count in sorted(stats["by_reason"].items(), key=lambda x: -x[1]):
        pct = count / stats["total_routes"] * 100
        lines.append(f"  {reason:20} {count:3} ({pct:5.1f}%)")
    
    return "\n".join(lines)
