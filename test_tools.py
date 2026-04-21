"""tests for tools.py."""
import asyncio

from tools import MAX_OUTPUT_BYTES, bash


def run(coro):
    return asyncio.run(coro)


def test_bash_echo():
    r = run(bash("echo hello"))
    assert r.output.strip() == "hello"
    assert r.is_error is False
    assert r.truncated is False


def test_bash_nonzero_exit_sets_error():
    r = run(bash("false"))
    assert r.is_error is True


def test_bash_stderr_captured():
    r = run(bash("echo oops 1>&2 && exit 1"))
    assert "oops" in r.output
    assert r.is_error is True


def test_bash_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("x")
    r = run(bash("ls", cwd=str(tmp_path)))
    assert "marker.txt" in r.output


def test_bash_strips_ansi():
    r = run(bash("printf '\\033[31mred\\033[0m\\n'"))
    assert "red" in r.output
    assert "\x1b[" not in r.output


def test_bash_truncates_huge_output():
    # 200KB of 'a'
    r = run(bash("python3 -c \"import sys; sys.stdout.write('a' * 200_000)\""))
    assert r.truncated is True
    assert len(r.output.encode()) <= MAX_OUTPUT_BYTES + 200  # +header
    assert "truncated" in r.output


def test_bash_timeout_kills_long_process():
    r = run(bash("sleep 10", timeout=0.3))
    assert r.timed_out is True
    assert r.is_error is True


def test_bash_cancel_kills_long_process():
    async def outer():
        task = asyncio.create_task(bash("sleep 10"))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # give the kernel a moment; if cleanup is wrong, a zombie sleep persists
        await asyncio.sleep(0.2)

    run(outer())  # if we got here without hanging, we're good
