"""TUI for mimicode — pi-style line-by-line chat, multi-line input, live footer."""
import os
import sys

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Label, RichLog, TextArea

from agent import agent_turn, load_messages, save_messages
from logger import log, start_session
from tools_session import all_sessions_token_usage, session_token_usage

# ---------------------------------------------------------------------------
# Palette — VS Code Dark+ inspired, mirrors pi-code's look
# ---------------------------------------------------------------------------
_BG       = "#1e1e1e"
_BG2      = "#252526"
_FG       = "#cccccc"
_DIM      = "#6a6a6a"
_USER     = "#569cd6"   # blue
_BOT      = "#4ec9b0"   # teal
_TOOL     = "#dcdcaa"   # yellow
_OK       = "#6a9955"   # green
_ERR      = "#f44747"   # red
_ACCENT   = "#007acc"


# ---------------------------------------------------------------------------
# PromptEditor — TextArea with Enter=submit, Shift+Enter=newline
# ---------------------------------------------------------------------------

class PromptEditor(TextArea):
    """Multi-line prompt input. Enter submits; Shift+Enter inserts a newline."""

    class Submitted(Message):
        def __init__(self, editor: "PromptEditor", value: str) -> None:
            self.editor = editor
            self.value = value
            super().__init__()

    DEFAULT_CSS = f"""
    PromptEditor {{
        height: auto;
        min-height: 3;
        max-height: 10;
        background: {_BG};
        color: {_FG};
        border: none;
        border-top: solid {_ACCENT};
        padding: 0 1;
    }}
    PromptEditor:focus {{
        border-top: solid {_USER};
    }}
    PromptEditor .text-area--cursor-line {{
        background: {_BG2};
    }}
    """

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(self, text))
                self.load_text("")
        elif event.key == "shift+enter":
            event.prevent_default()
            self.insert("\n")


# ---------------------------------------------------------------------------
# MimicodeApp
# ---------------------------------------------------------------------------

class MimicodeApp(App):
    """Mimicode TUI — pi-style line-by-line layout."""

    CSS = f"""
    Screen {{
        background: {_BG};
    }}
    #header {{
        background: {_BG2};
        color: {_DIM};
        height: 1;
        padding: 0 1;
    }}
    #chat {{
        height: 1fr;
        background: {_BG};
        padding: 0 1;
        scrollbar-size: 0 0;
    }}
    #thinking {{
        height: 1;
        background: {_BG};
        padding: 0 1;
        color: {_DIM};
        display: none;
    }}
    #thinking.active {{
        display: block;
    }}
    #footer-bar {{
        background: {_BG2};
        color: {_DIM};
        height: 1;
        padding: 0 1;
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+d", "quit", "Quit", show=False),
    ]

    def __init__(self, session_id: str | None = None) -> None:
        super().__init__()
        self.session = start_session(session_id)
        self.messages = load_messages(self.session.path)
        self.cwd = os.getcwd()
        self.is_processing = False

    def compose(self) -> ComposeResult:
        yield Label(
            f"mimicode  ·  {self.session.id}  ·  shift+enter for newline  ·  ctrl+c to quit",
            id="header",
        )
        yield RichLog(id="chat", markup=False, highlight=False, wrap=True, auto_scroll=True)
        yield Label(" ● thinking…", id="thinking")
        yield PromptEditor("", id="editor", language=None, show_line_numbers=False)
        yield Label("", id="footer-bar")

    def on_mount(self) -> None:
        log("tui_start", {
            "session_id": self.session.id,
            "cwd": self.cwd,
            "resumed": len(self.messages),
        })
        if self.messages:
            self._render_history()
            self._sys(f"resumed · {sum(1 for m in self.messages if m['role'] == 'user' and isinstance(m.get('content'), str))} prior turns")
        self._update_footer()
        self.query_one(PromptEditor).focus()

    # -----------------------------------------------------------------------
    # Chat write helpers — all use rich.text.Text, never raw markup strings
    # -----------------------------------------------------------------------

    def _log(self) -> RichLog:
        return self.query_one("#chat", RichLog)

    def _blank(self) -> None:
        self._log().write(Text(""))

    def _user(self, text: str) -> None:
        self._blank()
        lines = text.splitlines() or [""]
        for i, line in enumerate(lines):
            pfx = "you  " if i == 0 else "     "
            self._log().write(Text.assemble((pfx, f"bold {_USER}"), (line, _FG)))

    def _bot(self, text: str) -> None:
        if not text.strip():
            return
        self._blank()
        lines = text.splitlines() or [""]
        for i, line in enumerate(lines):
            pfx = " ●   " if i == 0 else "     "
            self._log().write(Text.assemble((pfx, f"bold {_BOT}"), (line, _FG)))

    def _tool_call(self, name: str, args: dict) -> None:
        parts = "  ".join(f"{k}={str(v)[:50]}" for k, v in (args or {}).items())
        if len(parts) > 90:
            parts = parts[:90] + "…"
        self._log().write(Text.assemble(
            (" ⚙   ", f"bold {_TOOL}"),
            (name + "  ", _TOOL),
            (parts, _DIM),
        ))

    def _tool_result(self, output: str, is_error: bool) -> None:
        icon  = " ✗   " if is_error else " ✓   "
        color = _ERR if is_error else _OK
        preview = output.replace("\n", "  ")[:120]
        if len(output) > 120:
            preview += f"…  ({len(output):,} chars)"
        self._log().write(Text.assemble((icon, f"bold {color}"), (preview, _DIM)))

    def _sys(self, text: str) -> None:
        self._log().write(Text.assemble(("     ", ""), (text, _DIM)))

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------

    def _update_footer(self) -> None:
        try:
            u = session_token_usage(self.session.path)
            total_k = (u["tokens_in"] + u["tokens_out"]) / 1000
            line = (
                f" claude-sonnet"
                f"  ·  {total_k:.1f}k tok"
                f"  ·  ${u['cost_usd']:.4f}"
                f"  ·  {self.session.id}"
            )
        except Exception:
            line = f" {self.session.id}"
        self.query_one("#footer-bar", Label).update(line)

    # -----------------------------------------------------------------------
    # History render
    # -----------------------------------------------------------------------

    def _render_history(self) -> None:
        for msg in self.messages:
            self._render_msg(msg)
        self._log().scroll_end(animate=False)

    def _render_msg(self, msg: dict) -> None:
        role    = msg.get("role")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, str):
                self._user(content)
            elif isinstance(content, list):
                for item in content:
                    if item.get("type") == "tool_result":
                        self._tool_result(item.get("content", ""), bool(item.get("is_error")))

        elif role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                t = block.get("type")
                if t == "text":
                    text_parts.append(block.get("text", ""))
                elif t == "tool_use":
                    self._tool_call(block["name"], block.get("input") or {})
            if text_parts:
                self._bot("\n".join(text_parts))

    # -----------------------------------------------------------------------
    # Slash commands
    # -----------------------------------------------------------------------

    def _slash(self, prompt: str) -> bool:
        cmd  = prompt.lower().split()[0]
        args = prompt.split()

        if cmd == "/help":
            self._blank()
            for line in [
                "  /help        show this message",
                "  /clear       clear chat history",
                "  /usage       token usage for this session",
                "  /usage all   token usage across all sessions",
            ]:
                self._sys(line)
            self._log().scroll_end(animate=True)
            return True

        if cmd == "/clear":
            self.messages = []
            self._log().clear()
            save_messages(self.session.path, self.messages)
            self._sys("chat cleared.")
            return True

        if cmd == "/usage":
            self._blank()
            if len(args) > 1 and args[1].lower() == "all":
                data = all_sessions_token_usage(self.session.path.parent)
                self._sys("token usage — all sessions")
                self._blank()
                for row in data["sessions"]:
                    self._sys(
                        f"  {row['session']:<22}"
                        f"  in {row['tokens_in']:>8,}"
                        f"  out {row['tokens_out']:>8,}"
                        f"  ${row['cost_usd']:.4f}"
                    )
                t = data["totals"]
                self._blank()
                self._sys(
                    f"  {'total':<22}"
                    f"  in {t['tokens_in']:>8,}"
                    f"  out {t['tokens_out']:>8,}"
                    f"  ${t['cost_usd']:.4f}"
                )
            else:
                u = session_token_usage(self.session.path)
                self._sys(f"token usage — {self.session.id}")
                self._blank()
                self._sys(f"  input         {u['tokens_in']:,}")
                self._sys(f"  output        {u['tokens_out']:,}")
                self._sys(f"  cache read    {u['cache_read']:,}")
                self._sys(f"  cache write   {u['cache_write']:,}")
                self._sys(f"  est. cost     ${u['cost_usd']:.4f}")
            self._log().scroll_end(animate=True)
            return True

        return False

    # -----------------------------------------------------------------------
    # Input
    # -----------------------------------------------------------------------

    async def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
        if self.is_processing:
            self.notify("agent is still working — please wait", severity="warning")
            return

        prompt  = event.value
        editor  = self.query_one(PromptEditor)
        thinking = self.query_one("#thinking", Label)

        if prompt.startswith("/"):
            if not self._slash(prompt):
                self._sys(f"unknown command: {prompt}  (try /help)")
                self._log().scroll_end(animate=True)
            return

        self._user(prompt)
        self._log().scroll_end(animate=True)

        thinking.add_class("active")
        editor.disabled = True
        self.is_processing = True

        # capture index before agent appends new messages
        turn_start = len(self.messages)

        try:
            self.messages = await agent_turn(
                prompt,
                messages=self.messages,
                cwd=self.cwd,
                session_id=self.session.id,
            )
            save_messages(self.session.path, self.messages)

            # render only what the agent produced this turn
            thinking.remove_class("active")
            for msg in self.messages[turn_start + 1:]:  # +1 skips the user msg we already rendered
                self._render_msg(msg)

        except Exception as e:
            thinking.remove_class("active")
            self._blank()
            self._sys(f"error: {e}")
            log("tui_error", {"error": str(e)})

        finally:
            thinking.remove_class("active")
            self._update_footer()
            self._log().scroll_end(animate=True)
            editor.disabled = False
            editor.focus()
            self.is_processing = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(session_id: str | None = None) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    MimicodeApp(session_id=session_id).run()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Mimicode TUI")
    p.add_argument("-s", "--session", help="Session ID")
    args = p.parse_args()
    main(session_id=args.session)
