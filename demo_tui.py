"""Demo script to showcase the TUI interface without requiring API key."""
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Input, Static, Label
from textual.binding import Binding


class DemoMessage(Static):
    """A demo message widget."""
    pass


class DemoApp(App):
    """Demo app showing the TUI layout."""
    
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
    
    #chat {
        height: 1fr;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    DemoMessage {
        margin: 0 0 1 0;
        padding: 1;
        background: $panel;
        border: solid $accent;
        height: auto;
    }
    
    DemoMessage.user {
        background: $primary-darken-2;
        border: solid $primary;
    }
    
    DemoMessage.assistant {
        background: $success-darken-2;
        border: solid $success;
    }
    
    DemoMessage.tool {
        background: $warning-darken-3;
        border: solid $warning;
        color: $text-muted;
    }
    
    #thinking {
        background: $boost;
        color: $text;
        padding: 1;
        margin: 0 1;
        height: auto;
    }
    
    #input {
        dock: bottom;
        border: solid $accent;
        margin: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
    ]
    
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Label("🤖 Mimicode TUI Demo - Session: demo123", id="title")
        yield VerticalScroll(id="chat")
        yield Static("🤖 Agent is thinking...", id="thinking")
        yield Input(placeholder="Type your prompt here and press Enter...", id="input")
        yield Footer()
    
    def on_mount(self) -> None:
        """Add demo messages on mount."""
        chat = self.query_one("#chat", VerticalScroll)
        
        # Demo conversation
        messages = [
            ("user", "👤 You: Create a hello world program in Python"),
            ("tool", "🔧 Using tool: write\nArgs: {'path': 'hello.py', 'content': 'print(\"Hello, World!\")'}"),
            ("tool", "🔧 Tool Result\n✅ Success\nCreated hello.py"),
            ("assistant", "🤖 Assistant:\nI've created a simple Python hello world program in `hello.py`.\nThe program prints 'Hello, World!' to the console."),
            ("user", "👤 You: Can you add a function to greet a person by name?"),
            ("tool", "🔧 Using tool: read\nArgs: {'path': 'hello.py'}"),
            ("tool", "🔧 Tool Result\n✅ Success\n1| print(\"Hello, World!\")"),
            ("tool", "🔧 Using tool: edit\nArgs: {'path': 'hello.py', 'old_text': 'print(\"Hello, World!\")', 'new_text': 'def greet(name):\\n    return f\"Hello, {name}!\"\\n\\nprint(greet(\"World\"))'}"),
            ("tool", "🔧 Tool Result\n✅ Success\nEdited hello.py"),
            ("assistant", "🤖 Assistant:\nI've updated the program to include a `greet()` function that takes a name parameter\nand returns a personalized greeting. The function uses an f-string for formatting."),
        ]
        
        for msg_type, content in messages:
            msg = DemoMessage(content)
            msg.add_class(msg_type)
            chat.mount(msg)
        
        chat.scroll_end(animate=False)
        
        # Hide thinking indicator in demo
        self.query_one("#thinking").display = False
        
        # Focus input
        self.query_one("#input", Input).focus()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle demo input."""
        if not event.value.strip():
            return
        
        chat = self.query_one("#chat", VerticalScroll)
        msg = DemoMessage(f"👤 You: {event.value}")
        msg.add_class("user")
        chat.mount(msg)
        
        # Add demo response
        response = DemoMessage("🤖 Assistant:\nThis is a demo. To use the real agent, run:\npython agent.py --tui")
        response.add_class("assistant")
        chat.mount(response)
        
        chat.scroll_end(animate=True)
        event.input.value = ""


def main():
    """Run the demo app."""
    print("=" * 60)
    print("Mimicode TUI Demo")
    print("=" * 60)
    print("\nThis is a demo showcasing the TUI interface.")
    print("To use the actual agent, run: python agent.py --tui")
    print("\nPress Ctrl+C to exit the demo.\n")
    
    app = DemoApp()
    app.run()


if __name__ == "__main__":
    main()
