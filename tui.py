"""TUI for mimicode — pi-style line-by-line chat, multi-line input, live footer."""
import asyncio
import os
import shutil
import sys
import random

from rich.text import Text
from rich.markdown import Markdown
from rich.padding import Padding
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, ScrollableContainer
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog, Static, TextArea

from agent import AgentInterrupted, _run_reflect, agent_turn, load_messages, save_messages
from logger import log, start_session
from providers import get_last_usage
from tools_router import analyze_routing, format_routing_stats
from tools_session import all_sessions_token_usage, session_token_usage
from session_history import add_to_history, get_most_recent, get_all, get_by_session_id
import compactor
from diff_display import create_file_diff, DiffLine

# ---------------------------------------------------------------------------
# Color Palettes
# ---------------------------------------------------------------------------

_PALETTES = {
    # Uses the terminal's own colours — no overrides
    "none": {
        "BG":     "default",
        "BG2":    "default",
        "FG":     "default",
        "DIM":    "bright_black",
        "USER":   "bright_blue",
        "BOT":    "bright_cyan",
        "TOOL":   "bright_yellow",
        "OK":     "bright_green",
        "ERR":    "bright_red",
        "ACCENT": "blue",
    },
    # Balanced neutral charcoal — good for any environment
    "default": {
        "BG":     "#1c1c1e",
        "BG2":    "#2c2c2e",
        "FG":     "#d1d1d6",
        "DIM":    "#6e6e73",
        "USER":   "#5ac8fa",
        "BOT":    "#32d74b",
        "TOOL":   "#ff9f0a",
        "OK":     "#32d74b",
        "ERR":    "#ff453a",
        "ACCENT": "#0a84ff",
    },
    # Near-black background, soft high-contrast text
    "dark": {
        "BG":     "#090909",
        "BG2":    "#141414",
        "FG":     "#ebebeb",
        "DIM":    "#4a4a4a",
        "USER":   "#c8c8c8",
        "BOT":    "#8db89a",
        "TOOL":   "#c8a96e",
        "OK":     "#5fad6f",
        "ERR":    "#c85a5a",
        "ACCENT": "#585858",
    },
    # White background, warm ink tones
    "light": {
        "BG":     "#ffffff",
        "BG2":    "#f2f2f7",
        "FG":     "#1c1c1e",
        "DIM":    "#8e8e93",
        "USER":   "#0071e3",
        "BOT":    "#1a8a3a",
        "TOOL":   "#b25000",
        "OK":     "#1a8a3a",
        "ERR":    "#d70015",
        "ACCENT": "#0071e3",
    },
    # Deep ocean: dark navy with cool blue accents
    "dark_blue": {
        "BG":     "#0a1628",
        "BG2":    "#0d1f3c",
        "FG":     "#cdd6f4",
        "DIM":    "#4a5270",
        "USER":   "#89b4fa",
        "BOT":    "#74c7ec",
        "TOOL":   "#f9e2af",
        "OK":     "#a6e3a1",
        "ERR":    "#f38ba8",
        "ACCENT": "#89b4fa",
    },
    # Sky and cloud: pale blue-white with deep blue ink
    "light_blue": {
        "BG":     "#eef2ff",
        "BG2":    "#dde6fb",
        "FG":     "#1e1b4b",
        "DIM":    "#7c87b0",
        "USER":   "#3730a3",
        "BOT":    "#0369a1",
        "TOOL":   "#6d28d9",
        "OK":     "#15803d",
        "ERR":    "#be123c",
        "ACCENT": "#4f46e5",
    },
}

# Current active palette
_CURRENT_PALETTE = "default"

def _get_color(key: str) -> str:
    """Get color from current palette."""
    return _PALETTES[_CURRENT_PALETTE][key]

# Color accessors
_BG     = lambda: _get_color("BG")
_BG2    = lambda: _get_color("BG2")
_FG     = lambda: _get_color("FG")
_DIM    = lambda: _get_color("DIM")
_USER   = lambda: _get_color("USER")
_BOT    = lambda: _get_color("BOT")
_TOOL   = lambda: _get_color("TOOL")
_OK     = lambda: _get_color("OK")
_ERR    = lambda: _get_color("ERR")
_ACCENT = lambda: _get_color("ACCENT")

# ---------------------------------------------------------------------------
# Tool action synonyms and animation
# ---------------------------------------------------------------------------
_ANIMATION_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Mouse-tracking escape sequences — disable to let the terminal do native selection
_MOUSE_TRACKING_OFF = "\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l"
_MOUSE_TRACKING_ON  = "\x1b[?1000h\x1b[?1003h\x1b[?1006h"

_TOOL_SYNONYMS = {
    "read": ["reading", "scanning", "parsing", "loading", "opening"],
    "write": ["writing", "creating", "saving", "generating", "composing"],
    "edit": ["editing", "modifying", "updating", "patching", "revising"],
    "bash": ["executing", "running", "invoking", "processing", "launching"],
    "memory_write": ["storing", "recording", "persisting", "archiving", "saving"],
}

def _get_tool_verb(tool_name: str) -> str:
    """Get a random synonym verb for the tool action."""
    synonyms = _TOOL_SYNONYMS.get(tool_name, [f"{tool_name}ing"])
    return random.choice(synonyms)

# ---------------------------------------------------------------------------
# Slash command registry
# ---------------------------------------------------------------------------
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help",      "show available commands"),
    ("/clear",     "clear chat history"),
    ("/exit",      "exit the application"),
    ("/new",       "start a fresh session"),
    ("/session",   "interactive session picker (or /session <name> to switch directly)"),
    ("/restore",   "restore last closed session (or /restore <session-id>)"),
    ("/usage",     "token usage — this session"),
    ("/usage all", "token usage — all sessions"),
    ("/cwd",       "change working directory"),
    ("/palette",   "change theme (none/default/dark/light/dark_blue/light_blue)"),
    ("/pmon",      "toggle prompt monitoring (warns on vague prompts)"),
    ("/compact",   "compact conversation now"),
    ("/compact on", "enable auto-compaction"),
    ("/compact off", "disable auto-compaction"),
    ("/compact status", "show compaction status"),
    ("/copy",      "copy last response to clipboard  (or ctrl+y)"),
    ("/select",    "toggle select mode for mouse text selection  (or f2)"),
]

def _has_subcommands(cmd: str) -> bool:
    """Check if a command has sub-commands in the SLASH_COMMANDS list."""
    # Commands with dynamic arguments (not fixed sub-commands) should not be treated as hierarchical
    DYNAMIC_ARG_COMMANDS = {"/session", "/palette", "/restore", "/cwd"}
    if cmd in DYNAMIC_ARG_COMMANDS:
        return False
    
    # A command has sub-commands if there's another command that starts with "cmd "
    cmd_prefix = cmd.rstrip() + " "
    return any(other_cmd.startswith(cmd_prefix) for other_cmd, _ in SLASH_COMMANDS if other_cmd != cmd)

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
# Session picker helpers
# ---------------------------------------------------------------------------

def _time_ago(mtime: float) -> str:
    """Convert a Unix mtime to a concise human-readable string."""
    import time as _t
    delta = _t.time() - mtime
    if delta < 60:     return "just now"
    if delta < 3600:   return f"{int(delta/60)}m ago"
    if delta < 86400:  return f"{int(delta/3600)}h ago"
    if delta < 604800: return f"{int(delta/86400)}d ago"
    return f"{int(delta/604800)}w ago"


def _session_preview(session_path) -> tuple[int, str]:
    """Return (turn_count, last_user_message_preview) from a session's messages file."""
    import json as _j
    mp = session_path.with_suffix(".messages.json")
    if not mp.exists():
        return 0, ""
    try:
        data = _j.loads(mp.read_text())
        if not isinstance(data, list):
            return 0, ""
        turns, last_msg = 0, ""
        for msg in data:
            if msg.get("role") == "user":
                c = msg.get("content", "")
                if isinstance(c, str) and c.strip():
                    turns += 1
                    last_msg = c.strip().replace("\n", " ")
        return turns, last_msg[:80]
    except Exception:
        return 0, ""


def _gather_session_metas(sessions_dir, current_id: str) -> list[dict]:
    """Collect metadata for all sessions in sessions_dir, sorted newest first."""
    paths = sorted(
        [p for p in sessions_dir.glob("*.jsonl") if not p.name.startswith(".")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    metas = []
    for path in paths:
        mtime = path.stat().st_mtime
        turns, last_msg = _session_preview(path)
        try:
            cost = session_token_usage(path)["cost_usd"]
        except Exception:
            cost = 0.0
        metas.append({
            "id":         path.stem,
            "mtime":      mtime,
            "turns":      turns,
            "last_msg":   last_msg,
            "cost":       cost,
            "is_current": path.stem == current_id,
        })
    return metas


# ---------------------------------------------------------------------------
# Session picker CSS + screen
# ---------------------------------------------------------------------------

def _get_session_picker_css() -> str:
    return f"""
    SessionPickerScreen {{
        align: center middle;
    }}
    #picker-box {{
        width: 96%;
        max-width: 120;
        height: 85%;
        background: {_BG2()};
        border: solid {_ACCENT()};
    }}
    #picker-title {{
        height: 1;
        background: {_ACCENT()};
        color: {_BG()};
        padding: 0 1;
        text-style: bold;
    }}
    #picker-filter {{
        height: 3;
        background: {_BG()};
        border: none;
        border-bottom: solid {_DIM()};
        color: {_FG()};
        padding: 0 1;
    }}
    #picker-filter:focus {{
        border-bottom: solid {_ACCENT()};
    }}
    #picker-scroll {{
        height: 1fr;
        background: {_BG2()};
    }}
    #picker-list {{
        height: auto;
        background: {_BG2()};
        padding: 0 0 0 0;
    }}
    #picker-help {{
        height: 1;
        background: {_BG2()};
        color: {_DIM()};
        padding: 0 1;
        border-top: solid {_DIM()};
    }}
    """


class SessionPickerInput(Input):
    """Custom Input that passes navigation keys to parent screen."""
    
    async def _on_key(self, event: events.Key) -> None:
        """Pass escape, up, down, enter to parent screen for navigation."""
        # Navigation keys should not be handled by Input - let them bubble to parent
        if event.key in ("escape", "up", "down", "enter"):
            return  # Don't handle, let parent screen handle
        # For all other keys, call parent Input's handler
        await super()._on_key(event)


class SessionPickerScreen(ModalScreen):
    """Claude Code-style interactive session picker."""

    BINDINGS = [
        Binding("escape", "cancel",      show=False, priority=True),
        Binding("up",     "cursor_up",   show=False, priority=True),
        Binding("down",   "cursor_down", show=False, priority=True),
        Binding("enter",  "confirm",     show=False, priority=True),
    ]

    def __init__(self, metas: list[dict]) -> None:
        SessionPickerScreen.DEFAULT_CSS = _get_session_picker_css()
        super().__init__()
        self._all_metas = metas
        self._displayed: list[dict | None] = []  # None = "new session" sentinel
        self._cursor = 0
        self._filter = ""
        self._rebuild()

    def _rebuild(self) -> None:
        f = self._filter.lower()
        filtered = [
            m for m in self._all_metas
            if not f or f in m["id"].lower() or f in (m["last_msg"] or "").lower()
        ]
        self._displayed = [None] + filtered
        self._cursor = max(0, min(self._cursor, len(self._displayed) - 1))

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Label(
                "  SESSIONS  ·  ↑↓ navigate  ·  Enter open  ·  type to filter  ·  Esc stay",
                id="picker-title",
            )
            yield SessionPickerInput(placeholder="  filter...", id="picker-filter")
            with ScrollableContainer(id="picker-scroll"):
                yield Static("", id="picker-list")
            yield Label(
                "  id                    age         turns  cost     last message",
                id="picker-help",
            )

    def on_mount(self) -> None:
        self._render_list()
        self.query_one(Input).focus()

    def _render_list(self) -> None:
        widget = self.query_one("#picker-list", Static)
        if not self._displayed:
            widget.update(Text("  (nothing matches)", style=_DIM()))
            return

        lines = Text()
        for i, item in enumerate(self._displayed):
            sel   = (i == self._cursor)
            arrow = "▶ " if sel else "  "

            if item is None:
                icon = "✦"
                row = Text.assemble(
                    (f"  {arrow}", f"bold {_ACCENT() if sel else _DIM()}"),
                    (f"{icon} new session", f"bold {_USER() if sel else _FG()}"),
                )
            else:
                sid      = item["id"]
                age      = _time_ago(item["mtime"])
                turns_s  = f"{item['turns']}t"
                cost_s   = f"${item['cost']:.3f}"
                preview  = (item["last_msg"] or "")[:50]
                mark     = " ←" if item["is_current"] else ""
                id_color = _ACCENT() if item["is_current"] else _FG()

                if sel:
                    row = Text.assemble(
                        (f"  {arrow}", f"bold {_ACCENT()}"),
                        (f"{sid:<20}", f"bold {id_color}"),
                        (f"  {age:<10}", _DIM()),
                        (f"  {turns_s:<6}", _DIM()),
                        (f"  {cost_s:<8}", _OK()),
                        (f"  {preview}", _FG()),
                        (mark, f"bold {_ACCENT()}"),
                    )
                else:
                    row = Text.assemble(
                        (f"  {arrow}", _DIM()),
                        (f"{sid:<20}", id_color),
                        (f"  {age:<10}", _DIM()),
                        (f"  {turns_s:<6}", _DIM()),
                        (f"  {cost_s:<8}", _DIM()),
                        (f"  {preview}", _DIM()),
                        (mark, _ACCENT()),
                    )

            lines.append_text(row)
            if i < len(self._displayed) - 1:
                lines.append("\n")

        widget.update(lines)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter = event.value
        self._cursor = 0
        self._rebuild()
        self._render_list()

    def on_key(self, event: events.Key) -> None:
        """Handle key events at screen level."""
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            # Find and return to current session
            current = next((m["id"] for m in self._all_metas if m.get("is_current")), None)
            self.dismiss(current)
        elif event.key == "up":
            event.prevent_default()
            event.stop()
            if self._cursor > 0:
                self._cursor -= 1
                self._render_list()
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            if self._cursor < len(self._displayed) - 1:
                self._cursor += 1
                self._render_list()
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            if not self._displayed:
                self.dismiss(None)
                return
            item = self._displayed[self._cursor]
            self.dismiss("__new__" if item is None else item["id"])
        else:
            # Pass unhandled keys to parent
            super().on_key(event)

    def action_cancel(self) -> None:
        """Cancel action - return to current session."""
        current = next((m["id"] for m in self._all_metas if m.get("is_current")), None)
        self.dismiss(current)

    def action_cursor_up(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self._render_list()

    def action_cursor_down(self) -> None:
        if self._cursor < len(self._displayed) - 1:
            self._cursor += 1
            self._render_list()

    def action_confirm(self) -> None:
        if not self._displayed:
            self.dismiss(None)
            return
        item = self._displayed[self._cursor]
        self.dismiss("__new__" if item is None else item["id"])


# ---------------------------------------------------------------------------
# PromptEditor
# ---------------------------------------------------------------------------

def _get_prompt_editor_css() -> str:
    """Generate PromptEditor CSS with current palette colors."""
    return f"""
    PromptEditor {{
        height: auto;
        min-height: 3;
        max-height: 10;
        background: {_BG()};
        color: {_FG()};
        border: none;
        border-top: solid {_ACCENT()};
        padding: 0 1;
    }}
    PromptEditor:focus {{
        border-top: solid {_USER()};
    }}
    PromptEditor .text-area--cursor-line {{
        background: {_BG2()};
    }}
    """

class PromptEditor(TextArea):
    """Multi-line input. Enter=submit, Shift+Enter=newline, Tab=autocomplete."""

    DEFAULT_CSS = _get_prompt_editor_css()

    class Submitted(Message):
        def __init__(self, editor: "PromptEditor", value: str) -> None:
            self.editor = editor
            self.value = value
            super().__init__()

    class TabPressed(Message):
        def __init__(self, editor: "PromptEditor") -> None:
            self.editor = editor
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._paste_content: dict[str, str] = {}
        self._history: list[str] = []
        self._history_index: int = 0
        self._draft: str = ""

    def _on_paste(self, event: events.Paste) -> None:
        """Intercept paste before TextArea processes it."""
        pasted_text = event.text
        lines = pasted_text.splitlines()

        if len(lines) > 1:
            event.prevent_default()
            event.stop()
            placeholder = f"[Pasted {len(lines)} lines]"
            self._paste_content[placeholder] = pasted_text
            self.insert(placeholder)
        else:
            super()._on_paste(event)

    def _on_key(self, event: events.Key) -> None:
        """Intercept keys before TextArea's default handling."""
        if event.key == "enter":
            # If autocomplete has matches, select the highlighted one
            current_completions = getattr(self.app, "_current_completions", [])
            if current_completions:
                event.prevent_default()
                event.stop()
                self.app.run_worker(self.app._select_completion(), exclusive=False)
                return
            # Otherwise submit the prompt
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                expanded_text = self._expand_paste_placeholders(text)
                self._history.append(text)
                self._history_index = len(self._history)
                self._draft = ""
                self.post_message(self.Submitted(self, expanded_text))
                self.load_text("")
                self._paste_content.clear()
        elif event.key == "up":
            if getattr(self.app, "_current_completions", []):
                event.prevent_default()
                event.stop()
                self.app._navigate_completion(-1)
                return
            row, _ = self.cursor_location
            if row == 0 and self._history_index > 0:
                event.prevent_default()
                event.stop()
                if self._history_index == len(self._history):
                    self._draft = self.text
                self._history_index -= 1
                self.load_text(self._history[self._history_index])
                self.move_cursor(self.document.end)
        elif event.key == "down":
            if getattr(self.app, "_current_completions", []):
                event.prevent_default()
                event.stop()
                self.app._navigate_completion(1)
                return
            row, _ = self.cursor_location
            if row == self.document.line_count - 1 and self._history_index < len(self._history):
                event.prevent_default()
                event.stop()
                self._history_index += 1
                if self._history_index == len(self._history):
                    self.load_text(self._draft)
                else:
                    self.load_text(self._history[self._history_index])
                self.move_cursor(self.document.end)
        elif event.key == "escape":
            # Hide autocomplete on Escape
            if getattr(self.app, "_current_completions", []):
                event.prevent_default()
                event.stop()
                self.app._hide_autocomplete()
                return
        elif event.key == "shift+enter":
            event.prevent_default()
            event.stop()
            self.insert("\n")
        elif event.key == "tab":
            event.prevent_default()
            event.stop()
            self.post_message(self.TabPressed(self))
        elif event.key == "backspace":
            row, col = self.cursor_location
            line_text = self.document.get_line(row)
            text_before = line_text[:col]
            for placeholder in list(self._paste_content.keys()):
                if text_before.endswith(placeholder):
                    event.prevent_default()
                    event.stop()
                    # Select the whole placeholder and delete it as one unit
                    self.move_cursor((row, col - len(placeholder)), select=True)
                    self.insert("")
                    del self._paste_content[placeholder]
                    return
    
    def _expand_paste_placeholders(self, text: str) -> str:
        """Replace all paste placeholders with their actual content."""
        expanded = text
        for placeholder, actual_content in self._paste_content.items():
            expanded = expanded.replace(placeholder, actual_content)
        return expanded


# ---------------------------------------------------------------------------
# AutocompleteBox
# ---------------------------------------------------------------------------

def _get_autocomplete_css() -> str:
    """Generate AutocompleteBox CSS with current palette colors."""
    return f"""
    AutocompleteBox {{
        background: {_BG2()};
        border: solid {_ACCENT()};
        padding: 0 1;
        height: auto;
        display: none;
    }}
    AutocompleteBox.visible {{
        display: block;
    }}
    """

class AutocompleteBox(Static):
    """Floating slash-command suggestions shown above the editor."""

    DEFAULT_CSS = _get_autocomplete_css()

    def show_completions(self, matches: list[tuple[str, str]], selected: int = 0) -> None:
        if not matches:
            self.remove_class("visible")
            return
        lines = Text()
        for i, (cmd, desc) in enumerate(matches):
            indicator = " → " if i == selected else "   "
            row = Text.assemble(
                (indicator, f"bold {_USER()}"),
                (f"{cmd:<20}", _FG() if i != selected else f"bold {_USER()}"),
                (f"  {desc}", _DIM()),
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

def _get_app_css() -> str:
    """Generate app CSS with current palette colors."""
    return f"""
    Screen {{
        background: {_BG()};
    }}
    #header {{
        background: {_BG2()};
        color: {_DIM()};
        height: 1;
        padding: 0 1;
    }}
    #chat {{
        height: 1fr;
        background: {_BG()};
        padding: 0 1;
        scrollbar-size: 0 0;
    }}
    #activity {{
        height: 2;
        background: {_BG()};
        padding: 0 1;
        display: none;
    }}
    #activity.active {{
        display: block;
    }}
    #pmon-warning {{
        background: #3d2e00;
        color: #f0c060;
        height: 1;
        padding: 0 1;
        display: none;
    }}
    #pmon-warning.visible {{
        display: block;
    }}
    #footer-bar {{
        background: {_BG2()};
        color: {_DIM()};
        height: 1;
        padding: 0 1;
    }}
    """

class MimicodeApp(App):
    """Mimicode TUI — pi-style layout."""

    CSS = _get_app_css()

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("escape", "interrupt_restore", "Interrupt+restore", show=False, priority=True),
        Binding("ctrl+y", "copy_last", "Copy", show=False, priority=True),
        Binding("f2", "toggle_select_mode", "Select", show=False),
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
        self._autocomplete_selected: int = 0
        self._current_text_blocks: dict[int, str] = {}
        self._current_tool_blocks: dict[int, dict] = {}
        self._interrupted: bool = False
        self._last_tool_name: str = ""
        self._last_tool_args: dict = {}
        self._last_tool_result: str | None = None
        self._last_tool_diff_info: dict | None = None
        self._animation_index: int = 0
        self._animation_timer: asyncio.Task | None = None
        self._pmon_enabled: bool = False
        self._pmon_warned: bool = False
        self._task_start_time: float | None = None
        self._tools_used_this_turn: bool = False
        self._truncated_diffs: dict[str, dict] = {}  # path -> {file_diff, max_lines_shown}
        self._last_bot_text: str = ""
        self._select_mode: bool = False

    def compose(self) -> ComposeResult:
        yield Label(
            f"mimicode  ·  {self.session.id}  ·  {self.cwd}  ·  shift+enter for newline  ·  ctrl+c interrupt  ·  esc interrupt+restore  ·  ctrl+y copy  ·  f2 select  ·  ctrl+d quit",
            id="header",
        )
        yield RichLog(id="chat", markup=False, highlight=False, wrap=True, auto_scroll=True)
        yield Static("", id="activity")
        yield AutocompleteBox(id="autocomplete")
        yield Static("", id="pmon-warning")
        yield PromptEditor("", id="editor", language=None, show_line_numbers=False)
        yield Label("", id="footer-bar")

    def on_key(self, event: events.Key) -> None:
        """Keep focus locked to the editor at all times (main screen only)."""
        if isinstance(self.screen, ModalScreen):
            return
        try:
            editor = self.query_one(PromptEditor)
        except Exception:
            return
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
        # Escape always exits select mode first
        if self._select_mode:
            self._select_mode = False
            self._write_terminal_seq(_MOUSE_TRACKING_ON)
            self._update_header()
            self._sys("select mode off.")
            self._log().scroll_end(animate=True)
            return
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
        self._stop_animation_timer()
        self._pmon_warned = False
        self._hide_pmon_warning()
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

    def _copy_to_clipboard(self, text: str) -> bool:
        """Write text to the system clipboard. Returns True on success."""
        import subprocess
        try:
            if sys.platform == "win32":
                subprocess.run(["clip"], input=text, text=True, encoding="utf-8", check=True)
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text, text=True, check=True)
            else:
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
                except FileNotFoundError:
                    subprocess.run(["xsel", "--clipboard", "--input"], input=text, text=True, check=True)
            return True
        except Exception:
            return False

    def action_copy_last(self) -> None:
        """Copy the last bot response to the system clipboard (Ctrl+Y)."""
        if not self._last_bot_text:
            self._sys("nothing to copy yet")
            self._log().scroll_end(animate=True)
            return
        if self._copy_to_clipboard(self._last_bot_text):
            self._sys("copied to clipboard.")
        else:
            self._sys("copy failed — clipboard tool not available")
        self._log().scroll_end(animate=True)

    def _write_terminal_seq(self, seq: str) -> None:
        """Write a raw VT escape sequence directly to the terminal device."""
        try:
            # sys.__stdout__ is the original stdout before any redirection
            out = sys.__stdout__
            if out is not None:
                out.write(seq)
                out.flush()
        except Exception:
            pass

    def action_toggle_select_mode(self) -> None:
        """Toggle select mode (F2): disable Textual mouse tracking so the terminal
        can do native text selection with click-and-drag."""
        self._select_mode = not self._select_mode
        if self._select_mode:
            self._write_terminal_seq(_MOUSE_TRACKING_OFF)
            self._update_header()
            self._sys(
                "SELECT MODE  —  drag to select · Ctrl+C or right-click to copy"
                " · F2 or Esc to return"
            )
        else:
            self._write_terminal_seq(_MOUSE_TRACKING_ON)
            self._update_header()
            self._sys("select mode off.")
        self._log().scroll_end(animate=True)

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
            self._tools_used_this_turn = True
            self._last_tool_name = tool_name
            self._last_tool_args = args
            self._last_tool_result = None
            self._set_activity(tool_name, args)

        elif event_type == "tool_exec_result":
            output   = data["output"]
            is_error = data["is_error"]
            diff_info = data.get("diff_info")
            args     = dict(self._last_tool_args)
            args["_is_error"] = is_error
            self._last_tool_result = output
            self._last_tool_diff_info = diff_info
            
            # Render tool result immediately with diff
            self._tool_call(self._last_tool_name, self._last_tool_args)
            self._tool_result(output, is_error, diff_info)
            self._log().scroll_end(animate=True)
            
            # Update activity widget
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
        
        # If not processing and starts with '/', search for matches
        if self.is_processing or not text.startswith("/"):
            self._current_completions = []
            self._autocomplete_selected = 0
            box.hide()
            return
        
        # Get the text after the slash
        if text.startswith("/session "):
            partial = text[len("/session "):]
            matches = self._session_completions(partial)
        elif text.startswith("/palette "):
            partial = text[len("/palette "):].strip()
            matches = [
                (f"/palette {name}", "current" if name == _CURRENT_PALETTE else "")
                for name in _PALETTES
                if name.startswith(partial)
            ]
        else:
            # For regular commands, match the prefix
            matches = _completions(text.strip())
        
        # Update completions and reset selection to first match
        if matches != self._current_completions:
            self._autocomplete_selected = 0
        self._current_completions = matches
        
        # Show or hide based on matches
        if matches:
            box.show_completions(matches, self._autocomplete_selected)
        else:
            box.hide()

    def _navigate_completion(self, direction: int) -> None:
        """Navigate to next/previous completion and update display."""
        if not self._current_completions:
            return
        self._autocomplete_selected = (self._autocomplete_selected + direction) % len(self._current_completions)
        # Update the display with new selection highlighted
        self.query_one(AutocompleteBox).show_completions(self._current_completions, self._autocomplete_selected)
    
    async def _select_completion(self) -> None:
        """Submit or navigate into the currently selected completion."""
        if not self._current_completions:
            return
        selected_cmd = self._current_completions[self._autocomplete_selected][0]
        editor = self.query_one(PromptEditor)
        
        # Check if this command has sub-commands
        if _has_subcommands(selected_cmd):
            # Navigate into sub-commands: fill the command with a trailing space
            editor.load_text(selected_cmd + " ")
            # The on_text_area_changed will trigger and show sub-command completions
        else:
            # No sub-commands: execute the command
            self._hide_autocomplete()
            
            # Special handling for commands that need async context
            if selected_cmd.strip().lower() == "/session":
                editor.load_text("")
                await self._open_session_picker()
            else:
                editor.load_text("")
                self.post_message(editor.Submitted(editor, selected_cmd))
    
    def _hide_autocomplete(self) -> None:
        """Hide the autocomplete box and clear state."""
        self._current_completions = []
        self._autocomplete_selected = 0
        self.query_one(AutocompleteBox).hide()

    def on_prompt_editor_tab_pressed(self, event: PromptEditor.TabPressed) -> None:
        if not self._current_completions:
            return
        self.run_worker(self._select_completion(), exclusive=False)

    # -----------------------------------------------------------------------
    # Chat write helpers — all use rich.text.Text, never raw markup strings
    # -----------------------------------------------------------------------

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        return f"{m}m {s}s" if s else f"{m}m"

    def _log(self) -> RichLog:
        return self.query_one("#chat", RichLog)

    def _blank(self) -> None:
        self._log().write(Text(""))

    def _user(self, text: str) -> None:
        self._blank()
        lines = text.splitlines() or [""]
        for i, line in enumerate(lines):
            pfx = "you  " if i == 0 else "     "
            self._log().write(Text.assemble((pfx, f"bold {_USER()}"), (line, _FG())))

    def _bot(self, text: str) -> None:
        if not text.strip():
            return
        self._last_bot_text = text
        self._blank()
        
        # Write the bot indicator prefix
        self._log().write(Text.assemble((" ●   ", f"bold {_BOT()}")))
        
        # Render markdown content with left padding for alignment
        md = Markdown(text)
        padded = Padding(md, (0, 0, 0, 5))  # 5 spaces to align with "     " continuation
        self._log().write(padded)

    def _tool_call(self, name: str, args: dict) -> None:
        parts = "  ".join(f"{k}={str(v)[:50]}" for k, v in (args or {}).items())
        if len(parts) > 90:
            parts = parts[:90] + "…"
        self._log().write(Text.assemble(
            (" ⚙   ", f"bold {_TOOL()}"),
            (name + "  ", _TOOL()),
            (parts, _DIM()),
        ))

    def _tool_result(self, output: str, is_error: bool, diff_info: dict | None = None) -> None:
        icon  = " ✗   " if is_error else " ✓   "
        color = _ERR() if is_error else _OK()
        
        # Skip redundant text output if we have a diff to show
        if not (diff_info and not is_error):
            preview = output.replace("\n", "  ")[:120]
            if len(output) > 120:
                preview += f"…  ({len(output):,} chars)"
            self._log().write(Text.assemble((icon, f"bold {color}"), (preview, _DIM())))
        else:
            # Just show success checkmark
            self._log().write(Text.assemble((icon, f"bold {color}"), ("File modified", _DIM())))
        
        # Display diff if available
        if diff_info and not is_error:
            self._render_diff(diff_info)
    
    def _render_diff(self, diff_info: dict, max_lines: int = 50) -> None:
        """Render a code diff with line-by-line changes."""
        try:
            path = diff_info.get("path", "")
            old_content = diff_info.get("old_content", "")
            new_content = diff_info.get("new_content", "")
            operation = diff_info.get("operation", "edit")
            is_new_file = diff_info.get("is_new_file", False)
            
            # Generate diff
            file_diff = create_file_diff(path, old_content, new_content, context=3)
            
            # Limit diff display for very large changes
            total_lines = len(file_diff.lines)
            display_lines = file_diff.lines[:max_lines]
            truncated = total_lines > max_lines
            
            # Store for potential expansion
            if truncated:
                self._truncated_diffs[path] = {
                    "file_diff": file_diff,
                    "diff_info": diff_info,
                    "max_lines_shown": max_lines
                }
            
            # Display diff header
            self._blank()
            header = f"━━━ {path} ({file_diff.summary}) ━━━"
            self._log().write(Text(header, style=f"bold {_ACCENT()}"))
            
            # Generate and show explanation at the top
            self._blank()
            explanation = self._generate_diff_explanation(file_diff, operation, is_new_file, old_content, new_content)
            self._log().write(Text.assemble(
                ("     ", ""),
                ("💡 ", _ACCENT()),
                (explanation, _DIM())
            ))
            self._blank()
            
            # Display diff lines
            for diff_line in display_lines:
                if diff_line.change_type == 'separator':
                    self._log().write(Text("     ⋮", style=_DIM()))
                    continue
                
                # Format line number
                if diff_line.change_type == 'add':
                    prefix = f" +{diff_line.line_num or '':>4} "
                    line_style = _OK()
                    symbol = "+"
                elif diff_line.change_type == 'delete':
                    prefix = f" -{diff_line.old_line_num or '':>4} "
                    line_style = _ERR()
                    symbol = "-"
                else:  # context
                    prefix = f"  {diff_line.line_num or '':>4} "
                    line_style = _DIM()
                    symbol = " "
                
                # Render the line
                self._log().write(Text.assemble(
                    (prefix, f"bold {line_style}"),
                    (symbol + " ", line_style),
                    (diff_line.content, _FG() if diff_line.change_type == 'context' else line_style)
                ))
            
            if truncated:
                remaining = total_lines - max_lines
                self._blank()
                self._log().write(Text.assemble(
                    ("     ", ""),
                    ("▼ ", _ACCENT()),
                    (f"{remaining} more lines hidden. ", _DIM()),
                    ("Type ", _DIM()),
                    (f"'expand {path}'", f"italic {_ACCENT()}"),
                    (" to view all or ", _DIM()),
                    (f"'expand {path} +50'", f"italic {_ACCENT()}"),
                    (" to show 50 more lines.", _DIM())
                ))
            
            self._blank()
        except Exception as e:
            # Silently fail if diff rendering fails - don't break the UI
            log("diff_render_error", {"error": str(e)})
    
    def _generate_diff_explanation(self, file_diff, operation: str, is_new_file: bool, 
                                   old_content: str, new_content: str) -> str:
        """Generate a human-readable explanation of what changed."""
        from diff_display import compute_diff_stats
        
        additions, deletions, _ = compute_diff_stats(file_diff.lines)
        
        if is_new_file:
            return f"Created new file with {additions} lines"
        elif operation == "write":
            if deletions == 0:
                return f"Wrote {additions} lines to file"
            else:
                return f"Overwrote file: {additions} lines added, {deletions} lines removed"
        else:  # edit
            # Analyze what changed to give specific feedback
            explanation_parts = []
            
            # Get the actual changed lines
            added_lines = [line.content for line in file_diff.lines if line.change_type == 'add']
            deleted_lines = [line.content for line in file_diff.lines if line.change_type == 'delete']
            
            # Basic stats
            if additions > 0 and deletions > 0:
                explanation_parts.append(f"Modified {max(additions, deletions)} line{'s' if max(additions, deletions) != 1 else ''}")
            elif additions > 0:
                explanation_parts.append(f"Added {additions} line{'s' if additions != 1 else ''}")
            elif deletions > 0:
                explanation_parts.append(f"Removed {deletions} line{'s' if deletions != 1 else ''}")
            
            # Try to identify what kind of change it was
            if added_lines:
                # Check for common patterns
                first_added = added_lines[0].strip() if added_lines else ""
                
                if first_added.startswith("def ") or first_added.startswith("async def "):
                    func_name = first_added.split("(")[0].replace("def ", "").replace("async ", "").strip()
                    explanation_parts.append(f"— defined function '{func_name}'")
                elif first_added.startswith("class "):
                    class_name = first_added.split("(")[0].split(":")[0].replace("class ", "").strip()
                    explanation_parts.append(f"— defined class '{class_name}'")
                elif first_added.startswith("import ") or first_added.startswith("from "):
                    explanation_parts.append(f"— added import statement")
                elif any(kw in first_added for kw in ["return ", "yield ", "raise "]):
                    explanation_parts.append(f"— modified control flow")
                elif "=" in first_added and not first_added.strip().startswith("#"):
                    var_name = first_added.split("=")[0].strip().split()[-1] if "=" in first_added else ""
                    if var_name and var_name.replace("_", "").isalnum():
                        explanation_parts.append(f"— set variable '{var_name}'")
            
            return " ".join(explanation_parts) if explanation_parts else "File modified"

    def _handle_expand_diff(self, prompt: str) -> None:
        """Handle 'expand <path> [+N]' command to show more diff lines."""
        parts = prompt.split()
        if len(parts) < 2:
            self._sys("usage: expand <path> [+N]  (e.g., 'expand tools.py' or 'expand tools.py +50')")
            self._log().scroll_end(animate=True)
            return
        
        path = parts[1]
        increment = 50  # default
        
        # Check for +N argument
        if len(parts) >= 3:
            try:
                inc_str = parts[2].replace("+", "")
                increment = int(inc_str)
                if increment <= 0:
                    raise ValueError
            except (ValueError, IndexError):
                self._sys(f"invalid increment: {parts[2]}  (use +N where N is a positive number)")
                self._log().scroll_end(animate=True)
                return
        
        # Find the diff
        if path not in self._truncated_diffs:
            self._sys(f"no truncated diff found for '{path}'")
            self._sys("(diffs are only expandable for the most recent file changes)")
            self._log().scroll_end(animate=True)
            return
        
        diff_data = self._truncated_diffs[path]
        current_max = diff_data["max_lines_shown"]
        
        # Check if we're already showing everything
        total_lines = len(diff_data["file_diff"].lines)
        if current_max >= total_lines:
            self._sys(f"'{path}' is already fully expanded ({total_lines} lines)")
            self._log().scroll_end(animate=True)
            return
        
        # Calculate new max
        new_max = min(current_max + increment, total_lines)
        if new_max == total_lines:
            self._sys(f"expanding '{path}' to show all {total_lines} lines...")
        else:
            self._sys(f"expanding '{path}' to show {new_max} of {total_lines} lines...")
        
        self._blank()
        
        # Re-render with new max
        self._render_diff(diff_data["diff_info"], max_lines=new_max)
        
        # Update stored max
        self._truncated_diffs[path]["max_lines_shown"] = new_max
        
        self._log().scroll_end(animate=True)

    def _sys(self, text: str) -> None:
        self._log().write(Text.assemble(("     ", ""), (text, _DIM())))

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------

    def _set_activity(self, tool_name: str | None = None, args: dict | None = None, result: str | None = None) -> None:
        """Update the live activity widget. tool_name=None means 'thinking'."""
        widget = self.query_one("#activity", Static)
        if tool_name is None:
            # Start animation for "thinking"
            self._start_animation_timer()
            widget.update(Text.assemble((" ●  ", f"bold {_BOT()}"), ("thinking…", _DIM())))
            widget.add_class("active")
            return
        
        key = _key_arg(tool_name, args or {})
        verb = _get_tool_verb(tool_name)
        anim_char = _ANIMATION_CHARS[self._animation_index % len(_ANIMATION_CHARS)]
        
        line1 = Text.assemble(
            (f" {anim_char}  ", f"bold {_TOOL()}"),
            (f"{verb}  ", _TOOL()),
            (key, _DIM()),
        )
        if result is not None:
            # Keep animation running even when showing results
            ok    = not (args or {}).get("_is_error")
            icon  = "✓" if ok else "✗"
            color = _OK() if ok else _ERR()
            preview = result.replace("\n", "  ")[:80] + ("…" if len(result) > 80 else "")
            anim_result = _ANIMATION_CHARS[self._animation_index % len(_ANIMATION_CHARS)]
            line2 = Text.assemble(
                (f" └─ {anim_result} {icon}  ", f"bold {color}"),
                (preview, _DIM()),
            )
        else:
            # Start animation for running tool
            self._start_animation_timer()
            anim_running = _ANIMATION_CHARS[self._animation_index % len(_ANIMATION_CHARS)]
            line2 = Text.assemble(
                (f" └─ {anim_running}  ", _DIM()), 
                ("processing…", _DIM())
            )
        content = Text()
        content.append_text(line1)
        content.append("\n")
        content.append_text(line2)
        widget.update(content)
        widget.add_class("active")

    def _clear_activity(self) -> None:
        self._stop_animation_timer()
        self._last_tool_name = ""
        self._last_tool_args = {}
        self._last_tool_result = None
        self._last_tool_diff_info = None
        widget = self.query_one("#activity", Static)
        widget.update(Text(""))
        widget.remove_class("active")
    
    def _start_animation_timer(self) -> None:
        """Start the animation timer if not already running."""
        if self._animation_timer is None or self._animation_timer.done():
            self._animation_timer = asyncio.create_task(self._animate_activity())
    
    def _stop_animation_timer(self) -> None:
        """Stop the animation timer."""
        if self._animation_timer and not self._animation_timer.done():
            self._animation_timer.cancel()
            self._animation_timer = None
    
    async def _animate_activity(self) -> None:
        """Continuously update the animation characters."""
        try:
            while True:
                await asyncio.sleep(0.1)  # 100ms per frame
                self._animation_index += 1
                # Re-render the activity line with updated animation
                if self._last_tool_name:
                    self._set_activity(self._last_tool_name, self._last_tool_args, result=self._last_tool_result)
                else:
                    # Update thinking animation
                    widget = self.query_one("#activity", Static)
                    anim_char = _ANIMATION_CHARS[self._animation_index % len(_ANIMATION_CHARS)]
                    widget.update(Text.assemble((f" {anim_char}  ", f"bold {_BOT()}"), ("thinking…", _DIM())))
        except asyncio.CancelledError:
            pass

    def refresh_css(self) -> None:
        """Refresh the CSS to apply new palette colors."""
        # Rebuild all CSS with new palette colors
        MimicodeApp.CSS = _get_app_css()
        PromptEditor.DEFAULT_CSS = _get_prompt_editor_css()
        AutocompleteBox.DEFAULT_CSS = _get_autocomplete_css()
        
        # Reparse the stylesheet
        try:
            self.stylesheet.reparse()
        except:
            # If reparse doesn't exist, try other methods
            pass
        
        # Trigger a full screen refresh
        self.refresh(layout=True, repaint=True)
        
    def _update_header(self) -> None:
        if self._select_mode:
            self.query_one("#header", Label).update(
                "[ SELECT MODE ]  drag to select · Ctrl+C or right-click to copy · F2 or Esc to exit"
            )
        else:
            self.query_one("#header", Label).update(
                f"mimicode  ·  {self.session.id}  ·  {self.cwd}  ·  shift+enter for newline"
                f"  ·  ctrl+c interrupt  ·  esc interrupt+restore  ·  ctrl+y copy  ·  f2 select  ·  ctrl+d quit"
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

    # -----------------------------------------------------------------------
    # Prompt monitoring
    # -----------------------------------------------------------------------

    _CONTINUATION = {
        "continue", "go", "ok", "okay", "yes", "yep", "sure", "proceed",
        "keep", "more", "next", "done", "thanks", "good", "great", "wait",
        "alright", "fine", "carry", "on",
    }
    _VAGUE_REFS = {"it", "this", "that", "those", "them", "stuff", "everything", "something"}
    _BARE_VERBS = {
        "fix", "update", "change", "improve", "edit", "refactor", "clean",
        "optimize", "rewrite", "check", "review", "make", "add", "remove",
        "delete", "get", "do", "run", "help",
    }

    def _needs_pmon_warning(self, prompt: str) -> bool:
        if not self._pmon_enabled:
            return False
        prior_replies = sum(1 for m in self.messages if m["role"] == "assistant")
        if prior_replies >= 2:
            return False
        words = prompt.lower().split()
        if not words:
            return False
        if all(w in self._CONTINUATION for w in words):
            return False
        if prior_replies == 0:
            if len(words) < 5:
                return True
            if len(words) < 10 and any(w in self._VAGUE_REFS for w in words):
                return True
            if len(words) <= 3 and words[0] in self._BARE_VERBS:
                return True
        return False

    def _show_pmon_warning(self) -> None:
        w = self.query_one("#pmon-warning", Static)
        w.update(
            " ⚠  Vague prompt — may waste tokens without more detail."
            "  Edit or press Enter to continue anyway."
            "  [ /pmon to disable ]"
        )
        w.add_class("visible")

    def _hide_pmon_warning(self) -> None:
        w = self.query_one("#pmon-warning", Static)
        w.update("")
        w.remove_class("visible")

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
    # Session management helpers
    # -----------------------------------------------------------------------

    def _do_new_session(self) -> None:
        add_to_history(self.session.id)
        self.session  = start_session()
        self.messages = []
        self._log().clear()
        self._update_header()
        self._update_footer()
        self._sys(f"new session · {self.session.id}")
        self._log().scroll_end(animate=True)

    def _do_switch_session(self, sid: str) -> None:
        if sid != self.session.id:
            add_to_history(self.session.id)
        self.session  = start_session(sid)
        self.messages = load_messages(self.session.path)
        self._log().clear()
        self._update_header()
        self._update_footer()
        if self.messages:
            self._render_history()
            n = sum(1 for m in self.messages if m["role"] == "user" and isinstance(m.get("content"), str))
            self._sys(f"switched · {sid} · {n} turns")
        else:
            self._sys(f"new session · {sid}")
        self._log().scroll_end(animate=True)

    async def _open_session_picker(self) -> None:
        metas  = _gather_session_metas(self.session.path.parent, self.session.id)
        result = await self.push_screen_wait(SessionPickerScreen(metas))
        if result is None:
            return
        # If user pressed Esc (returned current session), just stay in current session
        if result == self.session.id:
            return
        if result == "__new__":
            self._do_new_session()
        else:
            self._do_switch_session(result)

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
                "  /session           interactive session picker (↑↓ navigate, type to filter)",
                "  /session <name>    switch directly to a named session",
                "  /restore [id]      restore last closed session",
                "  /usage             token usage for this session",
                "  /usage all         token usage across all sessions",
                "  /route             show model routing stats (Haiku vs Sonnet)",
                "  /cwd [path]        change working directory (no arg = show current)",
                "  /palette <name>    change theme (none/default/dark/light/dark_blue/light_blue)",
                "  /pmon              toggle prompt monitoring (warns on vague prompts)",
                "  /compact           compact older turns now (or /compact on|off|status)",
                "  /copy              copy last response to clipboard  (also ctrl+y)",
                "  /select            toggle select mode: drag to select, Ctrl+C to copy  (also f2)",
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
            # Track session closure in history
            add_to_history(self.session.id)
            self.exit()
            return True

        if cmd == "/new":
            self._do_new_session()
            return True

        if cmd == "/session":
            if len(args) < 2:
                # no-arg /session is caught before _slash and opens the picker;
                # reaching here means trailing whitespace — treat same as no arg
                self._sys("tip: /session opens the session picker · /session <name> switches directly")
                self._log().scroll_end(animate=True)
                return True
            self._do_switch_session(args[1])
            return True

        if cmd == "/restore":
            history = get_all()
            
            if not history:
                self._blank()
                self._sys("no session history available")
                self._log().scroll_end(animate=True)
                return True
            
            # If a specific session ID is provided
            if len(args) >= 2:
                target_id = args[1]
                entry = get_by_session_id(target_id)
                
                if not entry:
                    self._blank()
                    self._sys(f"session '{target_id}' not found in recent history")
                    self._sys("available sessions:")
                    self._blank()
                    for i, hist_entry in enumerate(history, 1):
                        self._sys(f"  {i}. {hist_entry['session_id']:<24}  closed: {hist_entry['closed_at_str']}")
                    self._log().scroll_end(animate=True)
                    return True
                
                session_id_to_restore = entry["session_id"]
            else:
                # Restore the most recent session
                entry = get_most_recent()
                if not entry:
                    self._blank()
                    self._sys("no session history available")
                    self._log().scroll_end(animate=True)
                    return True
                session_id_to_restore = entry["session_id"]
            
            # Check if the session file still exists
            sessions_dir = self.session.path.parent
            session_path = sessions_dir / f"{session_id_to_restore}.jsonl"
            
            if not session_path.exists():
                self._blank()
                self._sys(f"session '{session_id_to_restore}' no longer exists")
                self._log().scroll_end(animate=True)
                return True
            
            self._sys(f"restoring session · {session_id_to_restore} · closed: {entry['closed_at_str']}")
            self._do_switch_session(session_id_to_restore)
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

        if cmd == "/route":
            self._blank()
            stats = analyze_routing(self.session.id)
            formatted = format_routing_stats(stats)
            self._sys("model routing — " + self.session.id)
            self._blank()
            for line in formatted.split("\n"):
                if line:
                    self._sys(line)
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

        if cmd == "/palette":
            global _CURRENT_PALETTE
            if len(args) < 2:
                # Show current palette and available options
                self._blank()
                self._sys(f"current theme: {_CURRENT_PALETTE}")
                self._sys(f"available themes: {', '.join(_PALETTES.keys())}")
                self._log().scroll_end(animate=True)
                return True
            
            palette_name = args[1].lower()
            if palette_name not in _PALETTES:
                self._sys(f"error: unknown theme '{palette_name}'")
                self._sys(f"available themes: {', '.join(_PALETTES.keys())}")
                self._log().scroll_end(animate=True)
                return True
            
            old_palette = _CURRENT_PALETTE
            _CURRENT_PALETTE = palette_name
            
            # Force a complete UI refresh by reloading CSS
            self.refresh_css()
            
            self._blank()
            self._sys(f"theme changed: {old_palette} → {palette_name}")
            if palette_name == "none":
                self._sys("using terminal's own colours")
            self._log().scroll_end(animate=True)
            log("palette_changed", {"old": old_palette, "new": palette_name, "session_id": self.session.id})
            return True

        if cmd == "/pmon":
            self._pmon_enabled = not self._pmon_enabled
            state = "on" if self._pmon_enabled else "off"
            self._sys(f"prompt monitoring {state}.")
            if not self._pmon_enabled:
                self._hide_pmon_warning()
                self._pmon_warned = False
            self._log().scroll_end(animate=True)
            return True

        if cmd == "/copy":
            self.action_copy_last()
            return True

        if cmd == "/select":
            self.action_toggle_select_mode()
            return True

        if cmd == "/compact":
            sub = args[1].lower() if len(args) >= 2 else ""
            if sub == "on":
                compactor.set_auto(True)
                self._sys("auto-compaction: on")
            elif sub == "off":
                compactor.set_auto(False)
                self._sys("auto-compaction: off")
            elif sub == "status":
                last_in = get_last_usage().get("tokens_in", 0)
                self._sys(compactor.status_text(self.session.path, last_in))
            elif sub == "":
                new_messages, record = compactor.compact(
                    self.messages, self.session.path, reason="manual"
                )
                if record is None:
                    self._sys("nothing to compact (need >2 user turns).")
                else:
                    self.messages = new_messages
                    save_messages(self.session.path, self.messages)
                    cid = record.get("id", "?")
                    rng = record.get("turn_range", ["?", "?"])
                    self._sys(f"compacted turns {rng[0]}–{rng[1]} -> {cid}")
                    self._update_footer()
            else:
                self._sys("usage: /compact | /compact on | /compact off | /compact status")
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

        # Handle expand command for diffs
        if prompt.strip().lower().startswith("expand "):
            self._handle_expand_diff(prompt.strip())
            return

        # Session picker needs async — intercept before sync _slash()
        if prompt.strip().lower() == "/session":
            await self._open_session_picker()
            return

        if prompt.startswith("/"):
            if not self._slash(prompt):
                self._sys(f"unknown command: {prompt}  (try /help)")
                self._log().scroll_end(animate=True)
            return

        if not self._pmon_warned and self._needs_pmon_warning(prompt):
            self._pmon_warned = True
            self._show_pmon_warning()
            return

        self._hide_pmon_warning()
        self._pmon_warned = False
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
        self._truncated_diffs.clear()  # Clear old diff expansion state
        self._task_start_time = asyncio.get_event_loop().time()
        self._tools_used_this_turn = False

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
                last_in = get_last_usage().get("tokens_in", 0)
                new_messages, record = compactor.maybe_compact(
                    self.messages, self.session.path, last_in
                )
                if record is not None:
                    self.messages = new_messages
                    save_messages(self.session.path, self.messages)
                    cid = record.get("id", "?")
                    reason = record.get("reason", "")
                    self._sys(f"[compacted: {reason} -> {cid}]")
                    self._update_footer()

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
                if self._tools_used_this_turn and self._task_start_time is not None:
                    elapsed = asyncio.get_event_loop().time() - self._task_start_time
                    self._sys(f"worked for {self._format_duration(elapsed)}")
                self._update_footer()
                self._log().scroll_end(animate=True)
                editor.disabled    = False
                editor.focus()
                self.is_processing = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(session_id: str | None = None) -> None:
    # Check for ripgrep (required dependency)
    if not shutil.which("rg"):
        print("error: ripgrep (rg) is not installed", file=sys.stderr)
        print("", file=sys.stderr)
        print("mimicode requires ripgrep for file searching.", file=sys.stderr)
        print("Install it with one of these methods:", file=sys.stderr)
        print("", file=sys.stderr)
        if sys.platform == "darwin":
            print("  macOS:  brew install ripgrep", file=sys.stderr)
        elif sys.platform.startswith("linux"):
            print("  Ubuntu/Debian:  sudo apt install ripgrep", file=sys.stderr)
            print("  Fedora/RHEL:    sudo dnf install ripgrep", file=sys.stderr)
            print("  Arch Linux:     sudo pacman -S ripgrep", file=sys.stderr)
        elif sys.platform == "win32":
            print("  Windows:  choco install ripgrep", file=sys.stderr)
            print("            scoop install ripgrep", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or download from: https://github.com/BurntSushi/ripgrep/releases", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run 'python3 check_deps.py' for a full dependency check.", file=sys.stderr)
        sys.exit(1)
    
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    app = MimicodeApp(session_id=session_id)
    app.run()
    _run_reflect(app.session.id, app.cwd)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Mimicode TUI")
    p.add_argument("-s", "--session", help="Session ID")
    args = p.parse_args()
    main(session_id=args.session)
