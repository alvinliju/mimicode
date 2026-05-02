# 🚀 Run Mimicode TUI Now!

## The Fastest Way to Start

### 1️⃣ Install Textual (if not already installed)
```bash
pip install textual
```

### 2️⃣ Make sure you have your API key set
```bash
# Linux/Mac/Git Bash
export ANTHROPIC_API_KEY=your_key_here

# Windows Command Prompt
set ANTHROPIC_API_KEY=your_key_here

# Windows PowerShell
$env:ANTHROPIC_API_KEY="your_key_here"
```

### 3️⃣ Launch the TUI
```bash
python agent.py --tui
```

That's it! 🎉

---

## Alternative: Use the Launcher (with automatic checks)
```bash
python tui_launcher.py
```
This will check if everything is set up correctly before launching.

---

## Try the Demo (No API Key Required)
Want to see what it looks like first?
```bash
python demo_tui.py
```

---

## Common Commands

```bash
# New session
python agent.py --tui

# Named session (will create or resume)
python agent.py --tui -s myproject

# Resume existing session
python agent.py --tui -s myproject
```

---

## Quick Help

**While using the TUI:**
- Type your message in the bottom box
- Press **Enter** to send
- Watch for "🤖 Agent is thinking..." 
- See responses appear in the chat
- Press **Ctrl+C** to exit

**Message colors:**
- 🔵 Blue = Your messages
- 🟢 Green = Agent responses
- 🟠 Orange = Tool usage & results

---

## Troubleshooting

### "No module named 'textual'"
```bash
pip install textual
```

### "ANTHROPIC_API_KEY not set"
Set the environment variable (see step 2 above)

### Display looks weird
- Use a modern terminal (Windows Terminal, iTerm2, etc.)
- Make sure your terminal is at least 80 characters wide

### Still having issues?
Check `TUI_README.md` for detailed troubleshooting

---

## Next Steps

Once you're comfortable with the TUI:
- Read `QUICKSTART_TUI.md` for more features
- See `TUI_VISUAL_GUIDE.md` for interface details
- Check `TUI_README.md` for advanced usage

**Happy coding! 🎨**
