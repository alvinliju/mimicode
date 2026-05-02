# mimicode

A minimal coding agent powered by Claude with a focus on deliberate, scoped tool use.

## Features

- **Four core tools**: `read`, `write`, `edit`, `bash` — nothing else
- **Session persistence**: Conversations and logs saved to JSONL for resume/replay
- **Prompt caching**: Efficient Claude API usage via Anthropic's prompt caching
- **Safety guardrails**: Blocks dangerous commands (`rm -rf /`, `curl | sh`, etc.)
- **Smart search enforcement**: Requires `rg` (ripgrep) instead of `find`/`grep -r`

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-key-here"  # Linux/Mac
# or
set ANTHROPIC_API_KEY=your-key-here       # Windows
```

## Usage

```bash
# One-shot prompt
python agent.py "your prompt"

# Named session (new or resume)
python agent.py -s mysession "your prompt"

# Resume session in REPL mode
python agent.py -s mysession

# New session in REPL mode
python agent.py
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
- Use `rg` for all searches (respects `.gitignore`)
- Read before editing
- Scope operations narrowly
- Never use banned commands (`find`, `grep -r`, `ls -R`, `cat` for code)

Tool output is capped at 100KB. If you hit that limit, your scope was too wide.

## License

MIT
