"""tests for agent.py loop. model is mocked; tools are real on tmp_path."""
import asyncio

import pytest

import agent


def run(coro):
    return asyncio.run(coro)


def _scripted_call_claude(responses):
    """returns a fake call_claude that yields each response in order."""
    it = iter(responses)

    async def fake(messages, system="", tools=None, **kwargs):
        try:
            return next(it)
        except StopIteration:
            return {"role": "assistant", "content": [{"type": "text", "text": "(no more)"}]}

    return fake


def test_turn_ends_when_no_tool_use(monkeypatch):
    monkeypatch.setattr(
        agent,
        "call_claude",
        _scripted_call_claude(
            [{"role": "assistant", "content": [{"type": "text", "text": "done"}]}]
        ),
    )
    msgs = run(agent.agent_turn("hi"))
    # [user, assistant]
    assert len(msgs) == 2
    assert msgs[-1]["content"][0]["text"] == "done"


def test_single_bash_tool_roundtrip(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("hello\n")
    monkeypatch.setattr(
        agent,
        "call_claude",
        _scripted_call_claude(
            [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "bash",
                            "input": {"cmd": "cat a.txt"},
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "file said hello"}],
                },
            ]
        ),
    )
    msgs = run(agent.agent_turn("read a.txt", cwd=str(tmp_path)))
    # user, assistant(tool_use), user(tool_result), assistant(text)
    assert len(msgs) == 4
    tool_result = msgs[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "t1"
    assert "hello" in tool_result["content"]
    assert msgs[-1]["content"][0]["text"] == "file said hello"


def test_unknown_tool_does_not_crash(monkeypatch):
    monkeypatch.setattr(
        agent,
        "call_claude",
        _scripted_call_claude(
            [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "nope", "input": {}}
                    ],
                },
                {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            ]
        ),
    )
    msgs = run(agent.agent_turn("x"))
    tool_result = msgs[2]["content"][0]
    assert tool_result["is_error"] is True
    assert "unknown tool" in tool_result["content"]


def test_max_steps_bail(monkeypatch):
    # always returns a tool call; loop should bail after max_steps
    def infinite():
        while True:
            yield {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "x", "name": "bash", "input": {"cmd": "true"}}],
            }

    gen = infinite()

    async def fake(messages, system="", tools=None, **kwargs):
        return next(gen)

    monkeypatch.setattr(agent, "call_claude", fake)
    msgs = run(agent.agent_turn("loop", max_steps=3))
    # 1 user + 3*(assistant + tool_result_user) = 7
    assert len(msgs) == 7


def test_parallel_tool_uses_in_one_response(monkeypatch, tmp_path):
    (tmp_path / "a").write_text("A")
    (tmp_path / "b").write_text("B")
    monkeypatch.setattr(
        agent,
        "call_claude",
        _scripted_call_claude(
            [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "a"}},
                        {"type": "tool_use", "id": "t2", "name": "read", "input": {"path": "b"}},
                    ],
                },
                {"role": "assistant", "content": [{"type": "text", "text": "got both"}]},
            ]
        ),
    )
    msgs = run(agent.agent_turn("read both", cwd=str(tmp_path)))
    results = msgs[2]["content"]
    assert len(results) == 2
    assert results[0]["tool_use_id"] == "t1"
    assert results[1]["tool_use_id"] == "t2"
    assert "A" in results[0]["content"]
    assert "B" in results[1]["content"]
