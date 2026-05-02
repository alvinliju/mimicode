# Quick Start: Mimicode TUI

Get started with the Mimicode TUI in under 2 minutes!

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `anthropic` - API client for Claude
- `textual` - Terminal UI framework
- `pytest` - For testing

## Step 2: Set API Key

```bash
# Linux/Mac
export ANTHROPIC_API_KEY=your_key_here

# Windows CMD
set ANTHROPIC_API_KEY=your_key_here

# Windows PowerShell
$env:ANTHROPIC_API_KEY="your_key_here"
```

## Step 3: Launch TUI

```bash
python agent.py --tui
```

## Step 4: Start Chatting!

1. Type your prompt in the input box at the bottom
2. Press **Enter** to send
3. Watch the "🤖 Agent is thinking..." indicator while it works
4. See the response appear in the chat history
5. Continue the conversation!

## Example Session

```
👤 You: Create a hello world program in Python

🤖 Agent is thinking...

🔧 Using tool: write
Args: {'path': 'hello.py', 'content': 'print("Hello, World!")'}

🔧 Tool Result
✅ Success
Created hello.py

🤖 Assistant:
I've created a simple Python hello world program in `hello.py`. 
The program prints "Hello, World!" to the console.
```

## Tips

- Press **Ctrl+C** to exit
- Use **-s session_name** to save and resume sessions
- Scroll up to see previous messages
- The agent can use tools: bash, read, write, edit

## Next Steps

- Try asking the agent to:
  - Create files and projects
  - Read and analyze code
  - Fix bugs
  - Run commands
  - Edit existing files

Enjoy coding with Mimicode! 🚀
