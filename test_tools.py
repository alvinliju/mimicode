"""tests for tools.py."""
import asyncio

import pytest

from tools import bash


def run(coro):
    return asyncio.run(coro)


def test_bash_echo():
    r = run(bash("echo hello"))
    assert r.output.strip() == "hello"
    assert r.is_error is False


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
