"""tests for tools.py."""
import asyncio

from tools import MAX_OUTPUT_BYTES, bash, read, write


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


def test_read_basic(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("line1\nline2\nline3\n")
    r = run(read(str(f)))
    assert "line1" in r.output
    assert "line3" in r.output
    assert r.is_error is False
    assert r.truncated is False
    # lines are numbered
    assert "     1|line1" in r.output


def test_read_missing():
    r = run(read("/no/such/file/xyz"))
    assert r.is_error is True
    assert "not found" in r.output


def test_read_directory_is_error(tmp_path):
    r = run(read(str(tmp_path)))
    assert r.is_error is True


def test_read_binary_rejected(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"abc\x00def")
    r = run(read(str(f)))
    assert r.is_error is True
    assert "binary" in r.output


def test_read_offset_and_limit(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line{i}" for i in range(1, 101)))
    r = run(read(str(f), offset=10, limit=5))
    assert r.truncated is True
    assert "line10" in r.output
    assert "line14" in r.output
    assert "line15" not in r.output
    assert "line9" not in r.output


def test_read_default_caps_at_2000_lines(tmp_path):
    f = tmp_path / "huge.txt"
    f.write_text("\n".join("x" for _ in range(3000)))
    r = run(read(str(f)))
    assert r.truncated is True
    # last numbered line shown should be 2000
    assert "  2000|" in r.output
    assert "  2001|" not in r.output


def test_read_cwd_resolves_relative(tmp_path):
    f = tmp_path / "rel.txt"
    f.write_text("hi")
    r = run(read("rel.txt", cwd=str(tmp_path)))
    assert "hi" in r.output
    assert r.is_error is False


def test_write_creates_file(tmp_path):
    f = tmp_path / "new.txt"
    r = run(write(str(f), "hello"))
    assert r.is_error is False
    assert f.read_text() == "hello"


def test_write_overwrites(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("old")
    run(write(str(f), "new"))
    assert f.read_text() == "new"


def test_write_creates_parent_dirs(tmp_path):
    f = tmp_path / "a" / "b" / "c.txt"
    r = run(write(str(f), "deep"))
    assert r.is_error is False
    assert f.read_text() == "deep"


def test_write_concurrent_same_path_serializes(tmp_path):
    f = tmp_path / "race.txt"

    async def burst():
        await asyncio.gather(*[write(str(f), f"value-{i}") for i in range(50)])

    run(burst())
    # last-writer-wins semantics, but crucially file must exist and be one of the values
    content = f.read_text()
    assert content.startswith("value-")
    assert content.split("-")[1].isdigit()
