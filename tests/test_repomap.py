"""tests for repomap.py."""
from __future__ import annotations

from pathlib import Path

from repomap import (
    CACHE_PATH,
    _extract_python,
    _is_low_priority,
    _truncate_to_budget,
    build_repo_map,
)


def test_extract_python_function_with_args():
    src = "def add(a, b, c=3):\n    return a + b + c\n"
    out = _extract_python(src)
    assert any("def add(a, b, c)" in line for line in out)


def test_extract_python_async_function():
    src = "async def fetch(url, timeout=5):\n    pass\n"
    out = _extract_python(src)
    assert any("async def fetch(url, timeout)" in line for line in out)


def test_extract_python_skips_private_top_level():
    src = "def public(): pass\ndef _private(): pass\n"
    out = _extract_python(src)
    assert any("def public()" in line for line in out)
    assert not any("_private" in line for line in out)


def test_extract_python_class_with_methods():
    src = "class Foo:\n    def bar(self): pass\n    def _hidden(self): pass\n    def __init__(self): pass\n"
    out = _extract_python(src)
    line = next(l for l in out if "class Foo" in l)
    assert "bar" in line
    assert "__init__" in line
    assert "_hidden" not in line


def test_extract_python_module_constants():
    src = "X = 1\nVERSION = '0.1'\n_HIDDEN = 2\nlowercase = 3\n"
    out = _extract_python(src)
    assert any("X" in line for line in out)
    assert any("VERSION" in line for line in out)
    assert not any(line.strip() == "_HIDDEN" for line in out)
    assert not any(line.strip() == "lowercase" for line in out)


def test_extract_python_handles_syntax_error():
    src = "def broken(:\n  pass\n"
    assert _extract_python(src) == []


def test_extract_python_varargs_and_kwargs():
    src = "def f(*args, **kwargs):\n    pass\n"
    out = _extract_python(src)
    assert any("def f(*args, **kwargs)" in line for line in out)


def test_truncate_to_budget_keeps_short_text():
    text = "line1\n\nline2"
    assert _truncate_to_budget(text, token_budget=100) == text


def test_truncate_to_budget_drops_sections_when_over():
    text = "\n\n".join(f"section_{i}" * 100 for i in range(5))
    out = _truncate_to_budget(text, token_budget=50)
    assert "[... " in out
    assert len(out) < len(text)


def test_is_low_priority_classifies_tests_and_fixtures():
    assert _is_low_priority("tests/test_foo.py")
    assert _is_low_priority("bench/fixtures/x/y.py")
    assert _is_low_priority("test_anything.py")
    assert not _is_low_priority("agent.py")
    assert not _is_low_priority("src/main.py")


def test_build_repo_map_writes_cache_and_reuses(tmp_path: Path):
    (tmp_path / "module.py").write_text("def hello():\n    return 1\n")
    out1 = build_repo_map(tmp_path)
    assert "def hello()" in out1
    cache = tmp_path / CACHE_PATH
    assert cache.exists()
    # tampering with source: cached content should win on subsequent call
    (tmp_path / "module.py").write_text("def goodbye():\n    return 2\n")
    out2 = build_repo_map(tmp_path)
    assert out2 == out1
    # forced refresh picks up the change
    out3 = build_repo_map(tmp_path, force_refresh=True)
    assert "def goodbye()" in out3


def test_build_repo_map_handles_missing_cwd(tmp_path: Path):
    """empty repo returns a string (possibly empty)."""
    out = build_repo_map(tmp_path)
    assert isinstance(out, str)


def test_build_repo_map_skips_unparseable_python(tmp_path: Path):
    (tmp_path / "good.py").write_text("def ok():\n    pass\n")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    out = build_repo_map(tmp_path)
    assert "good.py" in out
    assert "def ok()" in out
    # bad.py still appears as a path entry but with no symbols
    assert "bad.py" in out


def test_build_repo_map_low_priority_files_collapsed(tmp_path: Path):
    (tmp_path / "main.py").write_text("def app():\n    pass\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("def test_a():\n    pass\ndef test_b():\n    pass\n")
    out = build_repo_map(tmp_path)
    # production code keeps full symbol list
    assert "def app()" in out
    # tests collapse to "(N symbols)" form
    assert "tests/test_x.py" in out
    assert "(2 symbols)" in out
    assert "def test_a()" not in out
