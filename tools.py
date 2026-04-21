"""the four tools. bash, read, write, edit. nothing else."""
import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from logger import log

# strips CSI/OSC escape sequences. covers the 99% case for normal CLI output.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
MAX_OUTPUT_BYTES = 100_000  # ~100KB, anything beyond is tail-truncated
DEFAULT_READ_LINES = 2000  # default line cap for read(). match pi/claude code.

# pre-flight guardrail: patterns we refuse to run. each entry is (regex, reason).
# order matters — first match wins. we match command-name positions only
# (start of command or after |/;/&) to avoid false positives from quoted args.
_CMD_HEAD = r"(?:^|[|&;])\s*"  # command begins here
_BANNED: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(_CMD_HEAD + r"find\s+"),
     "use `rg --files` (respects .gitignore) instead of `find`"),
    (re.compile(_CMD_HEAD + r"grep\s+-[rR]\b"),
     "use `rg 'pattern'` instead of `grep -r`"),
    (re.compile(_CMD_HEAD + r"ls\s+-R\b"),
     "use `rg --files` instead of `ls -R`"),
    (re.compile(_CMD_HEAD + r"cat\s+\S+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java|c|cc|cpp|h|hpp|md|json|ya?ml|toml)\b"),
     "use the `read` tool (not `cat`) for code/config files"),
    (re.compile(r"\bcurl\s+[^|]*\|\s*(?:sh|bash)\b"),
     "refusing: `curl | sh` is unsafe"),
    (re.compile(_CMD_HEAD + r"rm\s+-rf?\s+(?:/|~|\*\s*$)"),
     "refusing: `rm -rf` on a dangerous target (/, ~, *)"),
)


def vet(cmd: str) -> str | None:
    """pre-flight check. returns a hint string if cmd is blocked, else None."""
    for pat, msg in _BANNED:
        if pat.search(cmd):
            return msg
    return None


def _clean(raw: bytes) -> str:
    """decode, strip ANSI, normalize newlines."""
    text = raw.decode("utf-8", errors="replace")
    text = _ANSI.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _truncate(text: str, limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    """keep the tail. return (text, truncated)."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    kept = data[-limit:].decode("utf-8", errors="replace")
    header = f"[... truncated {len(data) - limit} bytes; showing last {limit} ...]\n"
    return header + kept, True


@dataclass
class ToolResult:
    output: str
    is_error: bool = False
    truncated: bool = False
    timed_out: bool = False
    aborted: bool = False


async def _kill(proc: asyncio.subprocess.Process) -> None:
    """try terminate, then kill. never raise."""
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass


async def bash(cmd: str, cwd: str = ".", timeout: float | None = None) -> ToolResult:
    """run a shell command. combined stdout+stderr, ANSI stripped, tail-truncated.
    honors asyncio cancellation. kills the process on timeout or abort.
    pre-flight: vets against banned patterns (find, grep -r, etc.)."""
    hint = vet(cmd)
    if hint is not None:
        log("cmd_blocked", {"cmd": cmd[:200], "hint": hint})
        return ToolResult(output=f"[blocked] {hint}", is_error=True)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    timed_out = False
    aborted = False
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        await _kill(proc)
        stdout = b""
    except asyncio.CancelledError:
        aborted = True
        await _kill(proc)
        raise  # propagate cancellation after cleanup
    output, truncated = _truncate(_clean(stdout))
    rc = proc.returncode
    is_error = timed_out or aborted or (rc not in (0, None))
    # anthropic rejects tool_result with is_error=true and empty content.
    # synthesize a reason so the model has something to work with.
    if is_error and not output:
        if timed_out:
            output = f"[timeout after {timeout}s, no output]"
        elif aborted:
            output = "[aborted, no output]"
        else:
            output = f"[exit {rc}, no output]"
    return ToolResult(
        output=output,
        is_error=is_error,
        truncated=truncated,
        timed_out=timed_out,
        aborted=aborted,
    )


def _looks_binary(sample: bytes) -> bool:
    """heuristic: NUL byte in the first 8KB => binary."""
    return b"\x00" in sample


async def read(
    path: str,
    cwd: str = ".",
    offset: int = 1,
    limit: int | None = None,
) -> ToolResult:
    """read a text file. 1-indexed line offset + optional limit.
    refuses binary files. defaults to first 2000 lines.
    returns output prefixed with line numbers, truncation marker if capped."""
    abs_path = (Path(cwd) / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not abs_path.exists():
        return ToolResult(output=f"[error] not found: {path}", is_error=True)
    if abs_path.is_dir():
        return ToolResult(output=f"[error] is a directory: {path}", is_error=True)

    with abs_path.open("rb") as f:
        head = f.read(8192)
    if _looks_binary(head):
        return ToolResult(output=f"[error] binary file: {path}", is_error=True)

    text = abs_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    start = max(0, offset - 1)
    cap = limit if limit is not None else DEFAULT_READ_LINES
    end = min(total, start + cap)
    selected = lines[start:end]
    numbered = "\n".join(f"{start + i + 1:6d}|{line}" for i, line in enumerate(selected))
    truncated = end < total
    if truncated:
        numbered += f"\n[... showing lines {start + 1}-{end} of {total}; use offset/limit for more]"
    return ToolResult(output=numbered or "[empty file]", truncated=truncated)


# per-path mutation queue: serialize concurrent writes/edits to the same file.
_file_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _resolve(path: str, cwd: str) -> Path:
    p = Path(path)
    return p.resolve() if p.is_absolute() else (Path(cwd) / p).resolve()


async def write(path: str, content: str, cwd: str = ".") -> ToolResult:
    """create or overwrite a file. creates parent dirs. serialized per absolute path."""
    abs_path = _resolve(path, cwd)
    lock = _file_locks[str(abs_path)]
    async with lock:
        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(output=f"[error] {e}", is_error=True)
    return ToolResult(output=f"wrote {len(content)} bytes to {path}")


async def edit(path: str, old_text: str, new_text: str, cwd: str = ".") -> ToolResult:
    """surgical replace. old_text must match exactly once. serialized per path."""
    if old_text == new_text:
        return ToolResult(output="[error] old_text and new_text are identical", is_error=True)
    abs_path = _resolve(path, cwd)
    lock = _file_locks[str(abs_path)]
    async with lock:
        if not abs_path.exists():
            return ToolResult(output=f"[error] not found: {path}", is_error=True)
        try:
            original = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(output=f"[error] binary file: {path}", is_error=True)
        count = original.count(old_text)
        if count == 0:
            return ToolResult(output=f"[error] old_text not found in {path}", is_error=True)
        if count > 1:
            return ToolResult(
                output=f"[error] old_text matches {count} times in {path}; make it unique",
                is_error=True,
            )
        updated = original.replace(old_text, new_text, 1)
        abs_path.write_text(updated, encoding="utf-8")
        line = original[: original.index(old_text)].count("\n") + 1
    return ToolResult(output=f"edited {path} at line {line}")
