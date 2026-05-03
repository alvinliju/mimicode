"""a tiny tools module. nothing fancy."""
import asyncio


async def bash(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", "replace")


def read(path: str) -> str:
    with open(path) as f:
        return f.read()


def write(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)
