"""TUI (Text User Interface) for mimicode using Textual."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Input, Static, Label
from textual.binding import Binding

from logger import log, start_session
from agent import agent_turn, build_system, load_messages, save_messages


class MessageBox(Static):
    """A widget to display a single message."""
    pass


class ThinkingIndicator(Static):
    """Shows when the agent is working."""
    
    DEFAULT_CSS = """
    ThinkingIndicator {
        background: $boost;
        color: $text;
        padding: 1;
        margin: 0 1;
        height: auto;
        display: none;
    }
    
    ThinkingIndicator.active {
        display: block;
    }
    """
    
    def __init__(self):
        super().__init__("🤖 Agent is thinking...")
        self.add_class("thinking")


class ChatHistory(VerticalScroll):
    """Container for chat messages."""
    
    DEFAULT_CSS = """
    ChatHistory {
        height: 1fr;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    MessageBox {
        margin: 0 0 1 0;
        padding: 1;
        background: $panel;
        border: solid $accent;
        height: auto;
    }
    
    MessageBox.user {
        background: $primary-darken-2;
        border: solid $primary;
    }
    
    MessageBox.assistant {
        background: $success-darken-2;
        border: solid $success;
    }
    
    MessageBox.tool {
        background: $warning-darken-3;
        border: solid $warning;
        color: $text-muted;
    }
    """


class PromptInput(Input):
    """Input field for user prompts."""
    
    DEFAULT_CSS = """
    PromptInput {
        dock: bottom;
        border: solid $accent;
        margin: 1;
    }
    """


class MimicodeApp(App):
    """A Textual app for Mimicode."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #title {
        background: $primary;
        color: $text;
        padding: 1;
        text-align: center;
        height: auto;
        margin-bottom: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+d", "quit", "Quit", show=False),
    ]
    
    def __init__(self, session_id: str | None = None):
        super().__init__()
        self.session = start_session(session_id)
        self.messages = load_messages(self.session.path)
        self.cwd = os.getcwd()
        self.is_processing = False
        
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Label(f"🤖 Mimicode TUI - Session: {self.session.id}", id="title")
        yield ChatHistory()
        yield ThinkingIndicator()
        yield PromptInput(placeholder="Type your prompt here and press Enter...")
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        log("tui_start", {
            "session_id": self.session.id,
            "cwd": self.cwd,
            "resumed_messages": len(self.messages),
        })
        
        # Load existing messages
        if self.messages:
            self._render_all_messages()
            self.notify(f"Resumed session with {len(self.messages)} messages")
        
        # Focus on the input
        self.query_one(PromptInput).focus()
    
    def _render_all_messages(self) -> None:
        """Render all messages from history."""
        chat = self.query_one(ChatHistory)
        
        for msg in self.messages:
            if msg["role"] == "user":
                # Check if it's a tool result or a user prompt
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Tool results
                    for item in content:
                        if item.get("type") == "tool_result":
                            tool_msg = f"🔧 Tool Result (ID: {item['tool_use_id'][:8]}...)\n"
                            tool_msg += f"{'❌ Error' if item.get('is_error') else '✅ Success'}\n"
                            output = item.get("content", "")
                            # Truncate long outputs
                            if len(output) > 500:
                                output = output[:500] + f"\n... ({len(output)} chars total)"
                            tool_msg += output
                            box = MessageBox(tool_msg)
                            box.add_class("tool")
                            chat.mount(box)
                else:
                    # Regular user message
                    box = MessageBox(f"👤 You: {content}")
                    box.add_class("user")
                    chat.mount(box)
            
            elif msg["role"] == "assistant":
                # Extract text and tool uses
                content = msg.get("content", [])
                if isinstance(content, list):
                    text_parts = []
                    tool_uses = []
                    
                    for block in content:
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_uses.append(block)
                    
                    # Show text response
                    if text_parts:
                        text = "\n".join(text_parts)
                        box = MessageBox(f"🤖 Assistant:\n{text}")
                        box.add_class("assistant")
                        chat.mount(box)
                    
                    # Show tool uses
                    for tu in tool_uses:
                        tool_msg = f"🔧 Using tool: {tu['name']}\n"
                        tool_msg += f"Args: {tu.get('input', {})}"
                        box = MessageBox(tool_msg)
                        box.add_class("tool")
                        chat.mount(box)
        
        # Scroll to bottom
        chat.scroll_end(animate=False)
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        if self.is_processing:
            self.notify("Agent is still working, please wait...", severity="warning")
            return
        
        prompt = event.value.strip()
        if not prompt:
            return
        
        # Clear input
        input_widget = self.query_one(PromptInput)
        input_widget.value = ""
        
        # Add user message to chat
        chat = self.query_one(ChatHistory)
        user_box = MessageBox(f"👤 You: {prompt}")
        user_box.add_class("user")
        chat.mount(user_box)
        chat.scroll_end(animate=True)
        
        # Show thinking indicator
        thinking = self.query_one(ThinkingIndicator)
        thinking.add_class("active")
        
        # Disable input while processing
        input_widget.disabled = True
        self.is_processing = True
        
        try:
            # Run agent turn
            self.messages = await agent_turn(prompt, messages=self.messages, cwd=self.cwd)
            
            # Save messages
            save_messages(self.session.path, self.messages)
            
            # Display the assistant's response
            last_msg = self.messages[-1] if self.messages else None
            
            # Check if last message is tool results (user role)
            if last_msg and last_msg["role"] == "user":
                # Show tool results
                for item in last_msg.get("content", []):
                    if item.get("type") == "tool_result":
                        tool_msg = f"🔧 Tool Result (ID: {item['tool_use_id'][:8]}...)\n"
                        tool_msg += f"{'❌ Error' if item.get('is_error') else '✅ Success'}\n"
                        output = item.get("content", "")
                        if len(output) > 500:
                            output = output[:500] + f"\n... ({len(output)} chars total)"
                        tool_msg += output
                        box = MessageBox(tool_msg)
                        box.add_class("tool")
                        chat.mount(box)
                
                # Get the assistant message before tool results
                if len(self.messages) >= 2:
                    last_msg = self.messages[-2]
            
            # Display assistant message
            if last_msg and last_msg["role"] == "assistant":
                content = last_msg.get("content", [])
                if isinstance(content, list):
                    text_parts = []
                    tool_uses = []
                    
                    for block in content:
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_uses.append(block)
                    
                    # Show tool uses
                    for tu in tool_uses:
                        tool_msg = f"🔧 Using tool: {tu['name']}\n"
                        tool_msg += f"Args: {tu.get('input', {})}"
                        box = MessageBox(tool_msg)
                        box.add_class("tool")
                        chat.mount(box)
                    
                    # Show text response
                    if text_parts:
                        text = "\n".join(text_parts)
                        box = MessageBox(f"🤖 Assistant:\n{text}")
                        box.add_class("assistant")
                        chat.mount(box)
            
            chat.scroll_end(animate=True)
            
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")
            log("tui_error", {"error": str(e)})
            
            # Show error in chat
            error_box = MessageBox(f"❌ Error: {str(e)}")
            error_box.add_class("assistant")
            chat.mount(error_box)
            chat.scroll_end(animate=True)
        
        finally:
            # Hide thinking indicator
            thinking.remove_class("active")
            
            # Re-enable input
            input_widget.disabled = False
            input_widget.focus()
            self.is_processing = False


def main(session_id: str | None = None) -> None:
    """Run the TUI app."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    
    app = MimicodeApp(session_id=session_id)
    app.run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mimicode TUI")
    parser.add_argument("-s", "--session", help="Session ID (new or resume)")
    args = parser.parse_args()
    main(session_id=args.session)
