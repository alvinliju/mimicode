# mimicode

A minimal coding agent powered by Claude with a focus on deliberate, scoped tool use.

## Features

- **Four core tools**: `read`, `write`, `edit`, `bash` — nothing else
- **Session persistence**: Conversations and logs saved to JSONL for resume/replay
- **Prompt caching**: Efficient Claude API usage via Anthropic's prompt caching
- **Safety guardrails**: Blocks dangerous commands (`rm -rf /`, `curl | sh`, etc.)
- **Smart search enforcement**: Requires `rg` (ripgrep) instead of `find`/`grep -r`

## Quick Start

### Global Installation (Recommended)

Install mimicode globally and run it from anywhere:

```bash
# Install mimicode (updates PATH automatically)
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh | bash

# Set your API key (one time)
export ANTHROPIC_API_KEY="your-key-here"

# Run from any directory!
cd ~/my-project
mimicode
```

The installer will:
- Clone mimicode to `~/.mimicode`
- Create a global `mimicode` command
- Auto-setup virtual environment and dependencies
- Work on files in whatever directory you run it from

### Local Installation (Alternative)

Clone and run mimicode locally:

```bash
git clone https://github.com/Nihalsaeed/mimicode.git
cd mimicode
./mimicode
```

The `mimicode` launcher will:
1. Check that ripgrep and Python 3 are installed
2. Create a virtual environment (if needed)
3. Install Python dependencies automatically
4. Launch the TUI

### Prerequisites

You only need to install these system dependencies once:

1. **Python 3.8+** - [Download from python.org](https://www.python.org/downloads/)
2. **ripgrep** - Required for fast file searching:

```bash
# macOS
brew install ripgrep

# Ubuntu/Debian
sudo apt install ripgrep

# Fedora/RHEL
sudo dnf install ripgrep

# Arch Linux
sudo pacman -S ripgrep

# Windows (Chocolatey)
choco install ripgrep

# Windows (Scoop)
scoop install ripgrep

# Or download from: https://github.com/BurntSushi/ripgrep/releases
```

3. **Anthropic API Key** - Set your API key:

```bash
# Linux/Mac (add to ~/.bashrc or ~/.zshrc for persistence)
export ANTHROPIC_API_KEY="your-key-here"

# Windows
set ANTHROPIC_API_KEY=your-key-here
```

### Manual Setup (Alternative)

If you prefer manual control:

```bash
# Quick setup (checks dependencies and installs Python packages)
./setup.sh

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-key-here"

# Verify all dependencies
python3 check_deps.py
```

## Usage

### If Installed Globally

```bash
# Run from any directory
cd ~/my-project
mimicode

# The agent will work on files in your current directory
# Use /cwd command within TUI to change working directory
```

### If Running Locally

```bash
# Easy launcher (recommended)
./mimicode

# Or use agent.py directly:
# TUI mode
python agent.py --tui

# One-shot prompt
python agent.py "your prompt"

# Named session (new or resume)
python agent.py -s mysession "your prompt"

# Resume session in REPL mode
python agent.py -s mysession

# New session in REPL mode
python agent.py
```

## Updating & Uninstalling

### Update Global Installation

```bash
# Re-run the installer to update to latest version
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh | bash
```

### Uninstall

```bash
# Remove global installation
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/uninstall.sh | bash
```

## Architecture

- **agent.py** — Main loop and CLI entry point
- **tools.py** — Tool implementations with safety checks
- **providers.py** — Claude API wrapper with prompt caching
- **logger.py** — JSONL session logging (metadata only)
- **tools_session.py** — Session-aware tool wrappers

Sessions persist to:
- `sessions/<id>.jsonl` — Event stream (metadata)
- `sessions/<id>.messages.json` — Full conversation (for resume)

## Testing

```bash
pytest test_*.py
```

Test coverage includes:
- Tool validation and safety checks
- Logger session management
- Provider API interactions
- Agent loop behavior

## Philosophy

**Deliberate over broad.** The agent is trained to:
- Use `rg` (ripgrep) for all searches — it's faster than `grep` and respects `.gitignore` by default
- Read before editing
- Scope operations narrowly
- Never use banned commands (`find`, `grep -r`, `ls -R`, `cat` for code)

Tool output is capped at 100KB. If you hit that limit, your scope was too wide.

**Why ripgrep is required:** The agent's search rules enforce the use of `rg` instead of traditional tools like `find` and `grep -r`. This ensures searches are fast, scoped correctly, and respect `.gitignore` files. Without ripgrep installed, the agent cannot perform file searches.

## License

MIT
