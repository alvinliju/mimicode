"""TUI for mimicode — pi-style line-by-line chat, multi-line input, live footer."""
import asyncio
import os
import sys

from rich.text import Text
from rich.markdown import Markdown
from rich.padding import Padding
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Label, RichLog, Static, TextArea

from agent import AgentInterrupted, agent_turn, load_messages, save_messages
from logger import log, start_session
from tools_session import all_sessions_token_usage, session_token_usage

# ---------------------------------------------------------------------------
# Palette — VS Code Dark+ inspired
# ---------------------------------------------------------------------------
_BG     = "#1e1e1e"
_BG2    = "#252526"
_FG     = "#cccccc"
_DIM    = "#6a6a6a"
_USER   = "#569cd6"
_BOT    = "#4ec9b0"
_TOOL   = "#dcdcaa"
_OK     = "#6a9955"
_ERR    = "#f44747"
_ACCENT = "#007acc"

# ---------------------------------------------------------------------------
# Slash command registry
# ---------------------------------------------------------------------------
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help",      "show available commands"),
    ("/clear",     "clear chat history"),
    ("/exit",      "exit the application"),
    ("/new",       "start a fresh session"),
    ("/session",   "switch to or create a session"),
    ("/sessions",  "list all sessions"),
    ("/usage",     "token usage — this session"),
    ("/usage all", "token usage — all sessions"),
    ("/cwd",       "change working directory"),
]

def _completions(prefix: str) -> list[tuple[str, str]]:
    p = prefix.lower()
    return [(cmd, desc) for cmd, desc in SLASH_COMMANDS if cmd.startswith(p)]


def _key_arg(tool_name: str, args: dict) -> str:
    """Extract the most informative single argument for the activity line."""
    from pathlib import Path as _P
    if tool_name in ("read", "write", "edit"):
        p = args.get("path", "")
        return _P(p).name if p else ""
    if tool_name == "bash":
        cmd = args.get("cmd", "")
        return (cmd[:60] + "…") if len(cmd) > 60 else cmd
    return ""


# ---------------------------------------------------------------------------
# PromptEditor
# ---------------------------------------------------------------------------

class PromptEditor(TextArea):
    """Multi-line input. Enter=submit, Shift+Enter=newline, Tab=autocomplete."""

    class Submitted(Message):
        def __init__(self, editor: "PromptEditor", value: str) -> None:
            self.editor = editor
            self.value = value
            super().__init__()

    class TabPressed(Message):
        def __init__(self, editor: "PromptEditor") -> None:
            self.editor = editor
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
        elif event.key == "tab":
            event.prevent_default()
            self.post_message(self.TabPressed(self))


# ---------------------------------------------------------------------------
# AutocompleteBox
# ---------------------------------------------------------------------------

class AutocompleteBox(Static):
    """Floating slash-command suggestions shown above the editor."""

    DEFAULT_CSS = f"""
    AutocompleteBox {{
        background: {_BG2};
        border: solid {_ACCENT};
        padding: 0 1;
        height: auto;
        display: none;
    }}
    AutocompleteBox.visible {{
        display: block;
    }}
    """

    def show_completions(self, matches: list[tuple[str, str]]) -> None:
        if not matches:
            self.remove_class("visible")
            return
        lines = Text()
        for i, (cmd, desc) in enumerate(matches):
            indicator = " → " if i == 0 else "   "
            row = Text.assemble(
                (indicator, f"bold {_USER}"),
                (f"{cmd:<16}", _FG),
                (f"  {desc}", _DIM),
            )
            lines.append_text(row)
            if i < len(matches) - 1:
                lines.append("\n")
        self.update(lines)
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")


# ---------------------------------------------------------------------------
# MimicodeApp
# ---------------------------------------------------------------------------

class MimicodeApp(App):
    """Mimicode TUI — pi-style layout."""

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
    #activity {{
        height: 2;
        background: {_BG};
        padding: 0 1;
        display: none;
    }}
    #activity.active {{
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
        Binding("ctrl+d", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("escape", "interrupt_restore", "Interrupt+restore", show=False, priority=True),
    ]

    def __init__(self, session_id: str | None = None) -> None:
        super().__init__()
        self.session      = start_session(session_id)
        self.messages     = load_messages(self.session.path)
        self.cwd          = os.getcwd()
        self.is_processing = False
        self._last_prompt: str = ""
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._agent_task: asyncio.Task | None = None
        self._current_completions: list[tuple[str, str]] = []
        self._current_text_blocks: dict[int, str] = {}
        self._current_tool_blocks: dict[int, dict] = {}
        self._interrupted: bool = False
        self._last_tool_name: str = ""
        self._last_tool_args: dict = {}

    def compose(self) -> ComposeResult:
        yield Label(
            f"mimicode  ·  {self.session.id}  ·  {self.cwd}  ·  shift+enter for newline  ·  ctrl+c interrupt  ·  esc interrupt+restore  ·  ctrl+d quit",
            id="header",
        )
        yield RichLog(id="chat", markup=False, highlight=False, wrap=True, auto_scroll=True)
        yield Static("", id="activity")
        yield AutocompleteBox(id="autocomplete")
        yield PromptEditor("", id="editor", language=None, show_line_numbers=False)
        yield Label("", id="footer-bar")

    def on_key(self, event: events.Key) -> None:
        """Keep focus locked to the editor at all times."""
        editor = self.query_one(PromptEditor)
        # block tab/shift+tab from cycling focus to other widgets
        if event.key in ("tab", "shift+tab"):
            event.prevent_default()
            event.stop()
        # if focus drifted away (e.g. clicked RichLog), snap it back
        if self.focused is not editor:
            editor.focus()

    def on_mount(self) -> None:
        log("tui_start", {"session_id": self.session.id, "cwd": self.cwd, "resumed": len(self.messages)})
        if self.messages:
            self._render_history()
            n = sum(1 for m in self.messages if m["role"] == "user" and isinstance(m.get("content"), str))
            self._sys(f"resumed · {n} prior turns")
        self._update_footer()
        self.query_one(PromptEditor).focus()

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _do_interrupt(self, restore: bool = False) -> None:
        """Immediately cancel the agent task and restore UI. No waiting."""
        if not self.is_processing:
            if not restore:
                pass
            else:
                self.query_one(AutocompleteBox).hide()
            return
        self._cancel_event.set()
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
        self._interrupted = True
        editor  = self.query_one(PromptEditor)
        self._clear_activity()
        self._current_text_blocks.clear()
        self._current_tool_blocks.clear()
        self._blank()
        self._sys("interrupted.")
        self._update_footer()
        self._log().scroll_end(animate=True)
        editor.disabled = False
        editor.focus()
        self.is_processing = False
        if restore and self._last_prompt:
            editor.load_text(self._last_prompt)
            editor.move_cursor(editor.document.end)

    def action_interrupt(self) -> None:
        self._do_interrupt(restore=False)

    def action_interrupt_restore(self) -> None:
        self._do_interrupt(restore=True)

    # -----------------------------------------------------------------------
    # Streaming event handler
    # -----------------------------------------------------------------------

    async def _handle_stream_event(self, event_type: str, data: dict) -> None:
        """Handle real-time streaming events from the agent."""
        # Don't render anything if user has cancelled
        if self._cancel_event.is_set():
            return
        
        if event_type == "text_start":
            # New text block starting
            idx = data["index"]
            self._current_text_blocks[idx] = ""
        
        elif event_type == "text_delta":
            # Text chunk received - render immediately
            idx = data["index"]
            text_chunk = data["text"]
            self._current_text_blocks[idx] = self._current_text_blocks.get(idx, "") + text_chunk
            # For now, we'll just accumulate - full render happens at tool_start/tool_complete
        
        elif event_type == "tool_start":
            # Tool use block starting - track it
            idx = data["index"]
            tool_name = data["name"]
            self._current_tool_blocks[idx] = {
                "id": data["id"],
                "name": tool_name,
                "input": {},
            }
            # Render any accumulated text before showing the tool
            self._render_accumulated_text()
        
        elif event_type == "tool_complete":
            # Tool definition complete - store the full args
            idx = data["index"]
            self._current_tool_blocks[idx] = {
                "id": data["id"],
                "name": data["name"],
                "input": data["input"],
            }
        
        elif event_type == "tool_exec_start":
            tool_name = data["name"]
            args      = data["args"]
            self._last_tool_name = tool_name
            self._last_tool_args = args
            self._set_activity(tool_name, args)

        elif event_type == "tool_exec_result":
            output   = data["output"]
            is_error = data["is_error"]
            args     = dict(self._last_tool_args)
            args["_is_error"] = is_error
            self._set_activity(self._last_tool_name, args, result=output)
    
    def _render_accumulated_text(self) -> None:
        """Render any accumulated text blocks."""
        if self._current_text_blocks:
            full_text = "".join(self._current_text_blocks.values())
            if full_text.strip():
                self._bot(full_text)
            self._current_text_blocks.clear()

    # -----------------------------------------------------------------------
    # Autocomplete
    # -----------------------------------------------------------------------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        box  = self.query_one(AutocompleteBox)
        if self.is_processing or not text.startswith("/"):
            self._current_completions = []
            box.hide()
            return
        if text.startswith("/session "):
            partial = text[len("/session "):]
            matches = self._session_completions(partial)
        else:
            matches = _completions(text.strip())
        self._current_completions = matches
        box.show_completions(matches)

    def on_prompt_editor_tab_pressed(self, event: PromptEditor.TabPressed) -> None:
        if not self._current_completions:
            return
        top_cmd = self._current_completions[0][0]
        editor  = self.query_one(PromptEditor)
        editor.load_text(top_cmd)
        editor.move_cursor(editor.document.end)
        self._current_completions = []
        self.query_one(AutocompleteBox).hide()

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
        
        # Write the bot indicator prefix
        self._log().write(Text.assemble((" ●   ", f"bold {_BOT}")))
        
        # Render markdown content with left padding for alignment
        md = Markdown(text)
        padded = Padding(md, (0, 0, 0, 5))  # 5 spaces to align with "     " continuation
        self._log().write(padded)

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

    def _set_activity(self, tool_name: str | None = None, args: dict | None = None, result: str | None = None) -> None:
        """Update the live activity widget. tool_name=None means 'thinking'."""
        widget = self.query_one("#activity", Static)
        if tool_name is None:
            widget.update(Text.assemble((" ●  ", f"bold {_BOT}"), ("thinking…", _DIM)))
            widget.add_class("active")
            return
        key = _key_arg(tool_name, args or {})
        line1 = Text.assemble(
            (" ⚙  ", f"bold {_TOOL}"),
            (f"{tool_name}  ", _TOOL),
            (key, _DIM),
        )
        if result is not None:
            ok    = not (args or {}).get("_is_error")
            icon  = "✓" if ok else "✗"
            color = _OK if ok else _ERR
            preview = result.replace("\n", "  ")[:80] + ("…" if len(result) > 80 else "")
            line2 = Text.assemble(
                (f" └─ {icon}  ", f"bold {color}"),
                (preview, _DIM),
            )
        else:
            line2 = Text.assemble((" └─    ", _DIM), ("running…", _DIM))
        content = Text()
        content.append_text(line1)
        content.append("\n")
        content.append_text(line2)
        widget.update(content)
        widget.add_class("active")

    def _clear_activity(self) -> None:
        widget = self.query_one("#activity", Static)
        widget.update(Text(""))
        widget.remove_class("active")

    def _update_header(self) -> None:
        self.query_one("#header", Label).update(
            f"mimicode  ·  {self.session.id}  ·  {self.cwd}  ·  shift+enter for newline"
            f"  ·  ctrl+c interrupt  ·  esc interrupt+restore  ·  ctrl+d quit"
        )

    def _session_completions(self, partial: str) -> list[tuple[str, str]]:
        sessions_dir = self.session.path.parent
        ids = sorted(
            (p.stem for p in sessions_dir.glob("*.jsonl")),
            key=lambda sid: (sessions_dir / f"{sid}.jsonl").stat().st_mtime,
            reverse=True,
        )
        return [
            (f"/session {sid}", "current" if sid == self.session.id else "resume")
            for sid in ids if sid.startswith(partial)
        ]

    def _update_footer(self) -> None:
        try:
            u      = session_token_usage(self.session.path)
            total_k = (u["tokens_in"] + u["tokens_out"] + u["cache_read"] + u["cache_write"]) / 1000
            line   = (
                f" claude-sonnet"
                f"  ·  {total_k:.1f}k tok"
                f"  ·  ${u['cost_usd']:.4f}"
                f"  ·  {self.session.id}"
            )
        except Exception as e:
            log("footer_update_error", {"error": str(e), "session_path": str(self.session.path)})
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
                "  /help              show this message",
                "  /clear             clear chat history",
                "  /exit              exit the application",
                "  /new               start a fresh session",
                "  /session <name>    switch to or create a session",
                "  /sessions          list all sessions",
                "  /usage             token usage for this session",
                "  /usage all         token usage across all sessions",
                "  /cwd [path]        change working directory (no arg = show current)",
            ]:
                self._sys(line)
            self._log().scroll_end(animate=True)
            return True

        if cmd == "/clear":
            self.messages = []
            self._log().clear()
            save_messages(self.session.path, self.messages)
            self._sys("chat cleared.")
            self._update_footer()
            return True
        
        if cmd == "/exit":
            self._sys("exiting...")
            log("tui_exit", {"session_id": self.session.id, "via": "slash_command"})
            self.exit()
            return True

        if cmd == "/new":
            self.session  = start_session()
            self.messages = []
            self._log().clear()
            self._update_header()
            self._update_footer()
            self._sys(f"new session · {self.session.id}")
            self._log().scroll_end(animate=True)
            return True

        if cmd == "/session":
            if len(args) < 2:
                self._sys("usage: /session <name>")
                self._log().scroll_end(animate=True)
                return True
            sid = args[1]
            self.session  = start_session(sid)
            self.messages = load_messages(self.session.path)
            self._log().clear()
            self._update_header()
            self._update_footer()
            if self.messages:
                self._render_history()
                n = sum(1 for m in self.messages if m["role"] == "user" and isinstance(m.get("content"), str))
                self._sys(f"switched to {sid} · {n} prior turns")
            else:
                self._sys(f"new session · {sid}")
            self._log().scroll_end(animate=True)
            return True

        if cmd == "/sessions":
            sessions_dir = self.session.path.parent
            paths = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            self._blank()
            self._sys("sessions (most recent first)")
            self._blank()
            for path in paths:
                u   = session_token_usage(path)
                cur = "  ←" if path.stem == self.session.id else ""
                self._sys(f"  {path.stem:<24}  ${u['cost_usd']:.4f}{cur}")
            self._log().scroll_end(animate=True)
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

        if cmd == "/cwd":
            if len(args) < 2:
                # Show current working directory
                self._blank()
                self._sys(f"current working directory: {self.cwd}")
                self._log().scroll_end(animate=True)
                return True
            
            # Change to new directory
            new_path = " ".join(args[1:])  # support paths with spaces
            try:
                # Resolve and validate the path
                resolved = os.path.abspath(os.path.expanduser(new_path))
                if not os.path.isdir(resolved):
                    self._sys(f"error: not a directory: {new_path}")
                    self._log().scroll_end(animate=True)
                    return True
                
                old_cwd = self.cwd
                self.cwd = resolved
                os.chdir(self.cwd)  # Also change the process cwd
                self._update_header()
                self._blank()
                self._sys(f"changed working directory")
                self._sys(f"  from: {old_cwd}")
                self._sys(f"  to:   {self.cwd}")
                log("cwd_changed", {"old": old_cwd, "new": self.cwd, "session_id": self.session.id})
            except (OSError, ValueError) as e:
                self._sys(f"error changing directory: {e}")
            self._log().scroll_end(animate=True)
            return True

        return False

    # -----------------------------------------------------------------------
    # Input
    # -----------------------------------------------------------------------

    async def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
        if self.is_processing:
            self.notify("agent is still working — ctrl+c or esc to interrupt", severity="warning")
            return

        prompt = event.value
        editor = self.query_one(PromptEditor)

        self.query_one(AutocompleteBox).hide()

        if prompt.startswith("/"):
            if not self._slash(prompt):
                self._sys(f"unknown command: {prompt}  (try /help)")
                self._log().scroll_end(animate=True)
            return

        self._last_prompt = prompt
        self._user(prompt)
        self._log().scroll_end(animate=True)

        self._set_activity()
        editor.disabled    = True
        self.is_processing = True
        self._interrupted  = False
        self._cancel_event.clear()
        self._current_text_blocks.clear()
        self._current_tool_blocks.clear()

        messages_snapshot  = list(self.messages)
        self._agent_task   = asyncio.create_task(
            self._run_agent(prompt, messages_snapshot)
        )

    async def _run_agent(self, prompt: str, messages_snapshot: list) -> None:
        editor = self.query_one(PromptEditor)
        try:
            self.messages = await agent_turn(
                prompt,
                messages=self.messages,
                cwd=self.cwd,
                session_id=self.session.id,
                on_stream_event=self._handle_stream_event,
                cancel_event=self._cancel_event,
            )
            if not self._interrupted:
                save_messages(self.session.path, self.messages)
                self._render_accumulated_text()

        except (AgentInterrupted, asyncio.CancelledError):
            self.messages = messages_snapshot
            self._current_text_blocks.clear()
            self._current_tool_blocks.clear()
            if not self._interrupted:
                self._blank()
                self._sys("interrupted.")

        except Exception as e:
            if not self._interrupted:
                self._blank()
                self._sys(f"error: {e}")
                log("tui_error", {"error": str(e)})

        finally:
            self._agent_task = None
            if not self._interrupted:
                self._clear_activity()
                self._update_footer()
                self._log().scroll_end(animate=True)
                editor.disabled    = False
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
