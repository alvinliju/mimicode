"""the four tools. bash, read, write, edit. nothing else."""
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

# strips CSI/OSC escape sequences. covers the 99% case for normal CLI output.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
MAX_OUTPUT_BYTES = 100_000  # ~100KB, anything beyond is tail-truncated
DEFAULT_READ_LINES = 2000  # default line cap for read(). match pi/claude code.


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
    honors asyncio cancellation. kills the process on timeout or abort."""
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
    return ToolResult(
        output=output,
        is_error=timed_out or aborted or (proc.returncode not in (0, None)),
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
