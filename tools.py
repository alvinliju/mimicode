"""the four tools. bash, read, write, edit. nothing else."""
import asyncio
from dataclasses import dataclass


@dataclass
class ToolResult:
    output: str
    is_error: bool = False


async def bash(cmd: str, cwd: str = ".") -> ToolResult:
    """run a shell command. returns combined stdout+stderr."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace")
    return ToolResult(output=output, is_error=proc.returncode != 0)
