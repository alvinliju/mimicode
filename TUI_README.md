# Mimicode TUI (Text User Interface)

A beautiful terminal-based user interface for Mimicode that provides a chat-like experience for interacting with the AI coding agent.

## Features

- 🎨 **Clean Chat Interface**: Messages displayed in an easy-to-read format
- 💬 **Continuous Conversation**: Chat history is displayed and scrollable
- ⚡ **Real-time Feedback**: Visual indicator shows when the agent is processing
- 🔧 **Tool Visibility**: See which tools the agent is using and their results
- 💾 **Session Persistence**: Resume previous conversations seamlessly
- 🎯 **Keyboard Navigation**: Intuitive keyboard shortcuts

## Installation

First, install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Launch TUI Mode

```bash
# Start a new session
python agent.py --tui

# Resume or create a named session
python agent.py --tui -s mysession
```

### Keyboard Shortcuts

- **Enter**: Send your message
- **Ctrl+C** or **Ctrl+D**: Quit the application
- **Scroll**: Use mouse or arrow keys to scroll through chat history

## Interface Overview

The TUI consists of several components:

1. **Title Bar**: Shows the current session ID
2. **Chat History**: Scrollable area showing the conversation
   - 👤 **User messages**: Your prompts (blue background)
   - 🤖 **Assistant messages**: Agent responses (green background)
   - 🔧 **Tool calls**: Shows when the agent uses tools (yellow/orange background)
3. **Thinking Indicator**: Appears when the agent is processing (shows "🤖 Agent is thinking...")
4. **Input Box**: Where you type your prompts
5. **Footer**: Shows available keyboard shortcuts

## Message Types

The TUI displays different types of messages with visual distinctions:

- **User Prompts**: Your questions and requests
- **Assistant Responses**: Text responses from the AI agent
- **Tool Uses**: Shows which tools (bash, read, write, edit) are being called
- **Tool Results**: Shows the output or errors from tool executions

## Tips

- Long tool outputs are automatically truncated for readability
- The chat automatically scrolls to the latest message
- You can scroll up to review previous messages while the agent is working
- All conversations are saved and can be resumed later

## Comparison with CLI Mode

| Feature | CLI Mode | TUI Mode |
|---------|----------|----------|
| Interface | Plain text | Rich terminal UI |
| Chat History | Not visible | Scrollable view |
| Tool Feedback | Logged | Displayed inline |
| Visual Indicators | None | Thinking indicator |
| Session Resume | ✅ | ✅ |

## Troubleshooting

### Textual not installed
```bash
pip install textual
```

### Display issues
- Make sure your terminal supports Unicode characters
- Try resizing your terminal window
- Use a modern terminal emulator (Windows Terminal, iTerm2, etc.)

### ANTHROPIC_API_KEY not set
Make sure you have set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=your_key_here  # Linux/Mac
set ANTHROPIC_API_KEY=your_key_here     # Windows CMD
$env:ANTHROPIC_API_KEY="your_key_here"  # Windows PowerShell
```

## Development

The TUI is built using [Textual](https://textual.textualize.io/), a modern Python framework for building terminal user interfaces.

Main components:
- `tui.py`: Main TUI application code
- `agent.py`: Core agent logic (shared with CLI mode)
- Integration with existing session management and logging

## Future Enhancements

Potential improvements for the TUI:

- [ ] Syntax highlighting for code in messages
- [ ] File tree browser
- [ ] Split view for code editing
- [ ] Progress bars for long-running operations
- [ ] Export conversation to markdown
- [ ] Custom themes and colors
- [ ] Multiple conversation tabs
