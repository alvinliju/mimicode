"""bench runner. spins one tmpdir per task, runs agent.py, scores the result.

Usage:
  python -m bench.runner                      # run all tasks
  python -m bench.runner search_basic edit_single_line  # subset
  python -m bench.runner --model claude-sonnet-4-5-20250929
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bench.scorers import RunContext, bash_commands, final_text, metrics
from bench.tasks import TASKS, Task

ROOT = Path(__file__).resolve().parent.parent
AGENT_PY = ROOT / "agent.py"
FIXTURES = ROOT / "bench" / "fixtures"
RUNS_DIR = ROOT / "bench" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT_S = 180


def _load_env(root: Path) -> dict[str, str]:
    """crudely parse .env so subprocess inherits ANTHROPIC_API_KEY."""
    env = {}
    dotenv = root / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _git_sha(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _git_dirty(root: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        )
        return bool(out.decode().strip())
    except Exception:
        return False


def run_task(task: Task, model: str | None, timeout_s: int) -> dict:
    fixture = FIXTURES / task.fixture
    assert fixture.is_dir(), f"missing fixture: {fixture}"

    with tempfile.TemporaryDirectory(prefix=f"bench-{task.name}-") as td:
        cwd = Path(td)
        shutil.copytree(fixture, cwd, dirs_exist_ok=True)

        env = {**os.environ, **_load_env(ROOT)}
        if model:
            env["MIMICODE_MODEL"] = model  # not currently read; placeholder for future

        session_id = f"bench-{task.name}-{int(time.time())}"
        cmd = [sys.executable, str(AGENT_PY), "-s", session_id, task.prompt]

        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), env=env,
                capture_output=True, text=True, timeout=timeout_s,
            )
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            rc = -1
            timed_out = True
        elapsed = round(time.time() - t0, 2)

        global_sessions = Path.home() / ".mimi" / "sessions"
        session_jsonl = global_sessions / f"{session_id}.jsonl"
        messages_json = global_sessions / f"{session_id}.messages.json"
        events = []
        if session_jsonl.exists():
            for line in session_jsonl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        messages = []
        if messages_json.exists():
            try:
                messages = json.loads(messages_json.read_text())
            except Exception:
                pass

        ctx = RunContext(
            cwd=cwd, fixture=fixture, events=events, messages=messages,
            stdout=stdout, stderr=stderr, returncode=rc,
        )
        m = metrics(ctx)
        try:
            passed = bool(task.scorer(ctx))
        except Exception as e:
            passed = False
            m["scorer_error"] = f"{type(e).__name__}: {e}"

        result = {
            "task": task.name,
            "pass": passed,
            "wall_s": elapsed,
            "returncode": rc,
            "timed_out": timed_out,
            **m,
        }
        if os.environ.get("BENCH_DEBUG"):
            result["final_text"] = final_text(ctx)
            result["bash_cmds"] = bash_commands(ctx)
        return result


def run_bench(names: list[str], model: str | None, timeout_s: int) -> dict:
    tasks = [t for t in TASKS if not names or t.name in names]
    results = []
    for task in tasks:
        print(f"\n=== {task.name} ===", flush=True)
        print(f"prompt: {task.prompt}", flush=True)
        r = run_task(task, model=model, timeout_s=timeout_s)
        results.append(r)
        verdict = "PASS" if r["pass"] else "FAIL"
        mem_part = ""
        if r.get("memory_search", 0) or r.get("memory_write", 0):
            mem_part = f"mem_s={r.get('memory_search', 0)} mem_w={r.get('memory_write', 0)} "
        print(
            f"{verdict}  turns={r['turns']} steps={r['steps']} "
            f"bash={r['bash']} read={r['read']} edit={r['edit']} write={r['write']} "
            f"{mem_part}"
            f"blocked={r['cmd_blocked']} errs={r['tool_errors']} "
            f"tok_in={r['tokens_in']} tok_out={r['tokens_out']} "
            f"cache_r={r['cache_read']} cache_w={r['cache_write']} "
            f"${r['cost_usd']:.4f}  {r['wall_s']}s",
            flush=True,
        )

    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sha": _git_sha(ROOT),
        "dirty": _git_dirty(ROOT),
        "model": model or "default",
        "n_tasks": len(results),
        "n_pass": sum(1 for r in results if r["pass"]),
        "total_cost": round(sum(r["cost_usd"] for r in results), 5),
        "total_wall_s": round(sum(r["wall_s"] for r in results), 2),
        "results": results,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("names", nargs="*", help="task names (empty = all)")
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    args = p.parse_args(argv)

    summary = run_bench(args.names, args.model, args.timeout)

    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = RUNS_DIR / f"{stamp}-{summary['sha']}.json"
    out.write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY ===")
    print(f"sha:   {summary['sha']}{' (dirty)' if summary['dirty'] else ''}")
    print(f"pass:  {summary['n_pass']}/{summary['n_tasks']}")
    print(f"cost:  ${summary['total_cost']:.4f}")
    print(f"wall:  {summary['total_wall_s']}s")
    print(f"saved: {out.relative_to(ROOT)}")
    return 0 if summary["n_pass"] == summary["n_tasks"] else 1


if __name__ == "__main__":
    sys.exit(main())
