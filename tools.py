"""the four tools. bash, read, write, edit. nothing else."""
import asyncio
import re
from dataclasses import dataclass

# strips CSI/OSC escape sequences. covers the 99% case for normal CLI output.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
MAX_OUTPUT_BYTES = 100_000  # ~100KB, anything beyond is tail-truncated


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


async def bash(cmd: str, cwd: str = ".") -> ToolResult:
    """run a shell command. combined stdout+stderr, ANSI stripped, tail-truncated."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    stdout, _ = await proc.communicate()
    output, truncated = _truncate(_clean(stdout))
    return ToolResult(output=output, is_error=proc.returncode != 0, truncated=truncated)
