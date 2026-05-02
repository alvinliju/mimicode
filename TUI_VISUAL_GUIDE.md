# Mimicode TUI Visual Guide

## Interface Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  🤖 Mimicode TUI - Session: abc123                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Chat History (Scrollable)                                  │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ 👤 You: Create a hello world program in Python      │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ 🔧 Using tool: write                                 │ │ │
│  │  │ Args: {'path': 'hello.py', ...}                     │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ 🔧 Tool Result                                       │ │ │
│  │  │ ✅ Success                                           │ │ │
│  │  │ Created hello.py                                     │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ 🤖 Assistant:                                        │ │ │
│  │  │ I've created a simple Python hello world program    │ │ │
│  │  │ in `hello.py`. The program prints "Hello, World!"   │ │ │
│  │  │ to the console.                                      │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 🤖 Agent is thinking...                                    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Type your prompt here and press Enter...                   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ^C Quit                                                         │
└──────────────────────────────────────────────────────────────────┘
```

## Message Types

### 1. User Messages (Blue)
```
┌──────────────────────────────────────┐
│ 👤 You: Create a hello world program│
│        in Python                     │
└──────────────────────────────────────┘
```
- **Color**: Blue background
- **Icon**: 👤
- **Content**: Your prompt to the agent

### 2. Assistant Messages (Green)
```
┌─────────────────────────────────────────┐
│ 🤖 Assistant:                           │
│ I've created a simple Python hello      │
│ world program in `hello.py`.            │
└─────────────────────────────────────────┘
```
- **Color**: Green background
- **Icon**: 🤖
- **Content**: Agent's text response

### 3. Tool Use Messages (Yellow/Orange)
```
┌──────────────────────────────────────┐
│ 🔧 Using tool: write                 │
│ Args: {'path': 'hello.py', ...}      │
└──────────────────────────────────────┘
```
- **Color**: Orange background
- **Icon**: 🔧
- **Content**: Tool name and arguments

### 4. Tool Result Messages (Yellow/Orange)
```
┌──────────────────────────────────────┐
│ 🔧 Tool Result (ID: abc12345...)     │
│ ✅ Success                           │
│ Created hello.py                     │
└──────────────────────────────────────┘
```
- **Color**: Orange background
- **Icon**: 🔧
- **Status**: ✅ Success or ❌ Error
- **Content**: Tool output

## States

### Normal State
- Input box is active
- User can type and submit prompts
- Thinking indicator is hidden

### Processing State
```
┌────────────────────────────────────────┐
│ 🤖 Agent is thinking...                │
└────────────────────────────────────────┘
```
- Input box is disabled (grayed out)
- Thinking indicator is visible
- Chat auto-scrolls as new messages appear

### Error State
```
┌─────────────────────────────────────────┐
│ ❌ Error: Connection timeout            │
└─────────────────────────────────────────┘
```
- Error message displayed in chat
- Input box re-enabled
- User can retry or try different prompt

## Color Scheme

The TUI adapts to your terminal's theme but uses semantic colors:

| Element | Light Theme | Dark Theme |
|---------|-------------|------------|
| User messages | Light blue | Dark blue |
| Assistant | Light green | Dark green |
| Tool messages | Light orange | Dark orange |
| Background | Light gray | Dark gray |
| Borders | Accent color | Accent color |

## Interactive Elements

### Input Box
```
┌────────────────────────────────────────────────────┐
│ Type your prompt here and press Enter...          │
│ ▌                                                  │
└────────────────────────────────────────────────────┘
```
- Click to focus (or auto-focused)
- Type your message
- Press Enter to send
- Multi-line input supported (wrap automatically)

### Scrollable Chat
```
  ┌──────────────────────────┐
  │  [Older messages...]    ↑│
  │  [More messages...]      │
  │  [Recent messages...]    │
  │  [Latest message...]    ↓│
  └──────────────────────────┘
```
- Scroll with mouse wheel
- Arrow keys to navigate
- Auto-scroll to new messages
- Home/End keys for quick navigation

## Example Session Flow

### 1. Initial State
```
┌────────────────────────────────────────┐
│  🤖 Mimicode TUI - Session: new123    │
├────────────────────────────────────────┤
│  ┌──────────────────────────────────┐ │
│  │ [Empty chat history]             │ │
│  │                                  │ │
│  │                                  │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ Type your prompt here...▌        │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### 2. User Types
```
┌────────────────────────────────────────┐
│  ┌──────────────────────────────────┐ │
│  │ Create a hello world program▌    │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### 3. After Pressing Enter
```
┌────────────────────────────────────────┐
│  ┌──────────────────────────────────┐ │
│  │ 👤 You: Create a hello world     │ │
│  │        program                   │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🤖 Agent is thinking...          │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### 4. Agent Working
```
┌────────────────────────────────────────┐
│  ┌──────────────────────────────────┐ │
│  │ 👤 You: Create a hello world     │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🔧 Using tool: write             │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🔧 Tool Result: Success          │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🤖 Agent is thinking...          │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### 5. Complete Response
```
┌────────────────────────────────────────┐
│  ┌──────────────────────────────────┐ │
│  │ 👤 You: Create a hello world     │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🔧 Using tool: write             │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🔧 Tool Result: Success          │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ 🤖 Assistant:                    │ │
│  │ I've created hello.py...         │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ Type your next prompt here...▌   │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Send message |
| **Ctrl+C** | Quit application |
| **Ctrl+D** | Quit application |
| **↑/↓** | Scroll chat history |
| **Home** | Jump to top |
| **End** | Jump to bottom |
| **Mouse Wheel** | Scroll chat |

## Tips for Best Experience

1. **Terminal Size**: Recommended minimum 80x24 characters
2. **Font**: Use a monospace font with good Unicode support
3. **Colors**: Modern terminals show better colors (Windows Terminal, iTerm2)
4. **Scrolling**: The chat auto-scrolls, but you can scroll back anytime
5. **Sessions**: Use named sessions (-s) for organized work

## Comparison: CLI vs TUI

### CLI Mode
```
> Create a hello world program
[mimicode] session abc123 -> sessions/abc123.jsonl
I've created a simple Python hello world program...

> What files exist?
[mimicode] tool: bash ls
hello.py
The file hello.py exists in the current directory.
```

### TUI Mode
```
┌─────────────────────────────────────┐
│ 👤 You: Create a hello world        │
│ 🔧 Using tool: write                │
│ 🤖 Assistant: I've created...       │
│ 👤 You: What files exist?           │
│ 🔧 Using tool: bash                 │
│ 🤖 Assistant: The file hello.py...  │
│ ▌ Type next prompt...               │
└─────────────────────────────────────┘
```

**TUI Advantages:**
- Visual history always visible
- Color-coded messages
- Better context awareness
- Professional appearance
- Real-time feedback
