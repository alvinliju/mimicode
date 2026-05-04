# mimicode

**A lightweight, deliberate coding agent that gets real work done.**

mimicode is an AI coding assistant built on a simple principle: **constraints enable focus**. It uses four essential tools, always searches with ripgrep, intelligently routes between Claude Haiku and Sonnet, and remembers what it learns across sessions.

The result: a reliable, cost-effective (50–80% cheaper than always using top-tier models) AI assistant that stays predictable and auditable.

---

## Quick Start (2 minutes)

### One-line install (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/alvinliju/mimicode/main/install.sh | bash
```

**What it does:**
- Checks for Python 3.9+ (installs if needed)
- Installs ripgrep (via your package manager)
- Clones mimicode to `~/.local/mimicode`
- Creates a Python virtual environment
- Installs Python dependencies
- Adds `mimicode` command to your PATH

After installation, set your API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Then start using it:

```bash
mimicode --tui                 # Terminal UI (recommended)
mimicode "your prompt here"    # One-shot task
mimicode -s myproject          # Named session
```

### Manual Install (if you prefer)

Clone the repo and set up:

```bash
git clone https://github.com/alvinliju/mimicode.git
cd mimicode

# Install ripgrep
brew install ripgrep           # macOS
# or: sudo apt install ripgrep (Ubuntu/Debian)
# or: sudo dnf install ripgrep (Fedora/RHEL)

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python check_deps.py           # Verify everything

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run it
python agent.py --tui
```

### Windows

Use the PowerShell installer:

```powershell
irm https://trymimicode.github.io/install.ps1 | iex
```

Or install manually:
1. Install [Python 3.9+](https://www.python.org/downloads) (check "Add to PATH")
2. Install ripgrep: `choco install ripgrep` or `scoop install ripgrep`
3. `git clone https://github.com/alvinliju/mimicode.git && cd mimicode`
4. `python -m venv .venv && .venv\Scripts\activate`
5. `pip install -r requirements.txt`
6. `python agent.py --tui`

---

## The Four Tools

mimicode gives you **exactly four tools**, each with purpose-built constraints:

### 1. `read(path, offset?, limit?)`

Read file contents safely and deliberately.

```python
read("src/main.py")                # First 2000 lines (default)
read("src/main.py", offset=100)    # Start from line 100
read("src/main.py", limit=50)      # Read 50 lines from offset
```

**Why these constraints?**
- Max 2000 lines by default → forces specificity (no reading 50K-line files)
- Line-numbered output → easier to navigate
- Text files only, binary-safe → prevents accidents
- ~100KB output cap → keeps responses focused

### 2. `write(path, content)`

Create or completely replace file contents.

```python
write("src/new_file.py", "def hello(): pass")
write("config.json", json_content)
```

**When to use:** New files or complete rewrites. For changes to existing code, prefer `edit`.

**Why this design?**
- Auto-creates parent directories
- Explicit content (no hidden appends)
- Forces you to think about full file contents
- Pairs well with `read` (read first, then write)

### 3. `edit(path, old_text, new_text)` or `edits=[...]`

Surgical code changes with exact text matching.

```python
# Single edit
edit("src/main.py", 
     old_text="def route_model():",
     new_text="def select_model():")

# Multiple edits in same file (atomic)
edit("src/main.py", edits=[
    {
        "old_text": "def route_model():",
        "new_text": "def select_model():"
    },
    {
        "old_text": "route_model(x)",
        "new_text": "select_model(x)"
    }
])
```

**Key rules:**
- Must match `old_text` exactly (whitespace counts)
- Include 2–3 lines of surrounding context
- Prevents off-by-one errors
- Batch edits are **atomic** (all succeed or none apply)

### 4. `bash(cmd, timeout?)`

Run shell commands with output capture.

```python
bash("pytest -xvs tests/")
bash("rg 'pattern' --type py", timeout=10)
bash("python scripts/build.py")
```

**Safety guarantees:**
- Pre-flight validation blocks dangerous patterns:
  - `find`, `grep -r`, `ls -R` (use `rg` instead)
  - `curl | sh` (pipe to shell)
  - `rm -rf /` or `rm -rf ~` (catastrophic deletion)
- 30-second timeout by default
- ANSI codes stripped from output
- Combined stdout + stderr

---

## Smart Model Routing

mimicode automatically picks the right Claude model for each task:

| Task Type | Model | Why |
|-----------|-------|-----|
| First turn, complex questions | **Sonnet** | Needs full understanding |
| Simple reads, searches | **Haiku** | Fast and cheap |
| Single-file edits | **Haiku** | Straightforward |
| Run tests, execute commands | **Haiku** | Just execution |
| Refactoring, architecture | **Sonnet** | Needs reasoning |
| Debugging errors | **Sonnet** | Complex problem-solving |

**Cost impact:**
- All Sonnet: baseline (100%)
- With smart routing: **50–80% savings**

Real example: a 10-turn session with 70% Haiku, 30% Sonnet costs ~50% less than all-Sonnet.

See [ROUTING.md](ROUTING.md) for detailed routing logic.

---

## Ripgrep: The Search Standard

Instead of `find`, `grep -r`, `ls -R`, or `cat`:

```bash
# List files in the repo
rg --files

# Search for a pattern
rg 'pattern'

# Search Python files only
rg 'pattern' -t py

# With line numbers
rg -n 'pattern'

# In a specific directory
rg 'pattern' src/

# Case-insensitive
rg -i 'pattern'

# Find matching files only
rg -l 'pattern'
```

**Why ripgrep?**
- ~10x faster than grep
- Respects `.gitignore` by default (no `node_modules/`, `.venv/`, etc.)
- Cleaner output
- Required by mimicode (agent will refuse to use alternatives)

**Automatically excluded:** `.venv/`, `.git/`, `node_modules/`, `__pycache__/`, `dist/`, `build/`, `.pytest_cache/`

---

## Sessions & Persistence

Each session is a complete, resumable conversation:

```bash
# Create a new named session
python agent.py -s myproject "Add logging to router.py"

# Resume the same session later
python agent.py -s myproject "Increase timeout from 30s to 60s"

# List all sessions
ls sessions/
```

### What Gets Saved

Each session produces:

**`sessions/<id>.jsonl`** — Event stream (one per action)
```jsonl
{"kind": "user_msg", "turn": 1, "content": "..."}
{"kind": "model_route", "model": "haiku", "reason": "simple_edit"}
{"kind": "tool_use", "tool": "read", "args": {"path": "router.py"}}
{"kind": "tool_result", "output": "..."}
```

**`sessions/<id>.messages.json`** — Full conversation (for resuming)
```json
[
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "...", "tool_use": [{...}]},
  ...
]
```

Use these to:
- Understand exactly what the agent did and why
- Debug failures (see full tool output)
- Replay conversations
- Analyze costs per turn

---

## Cross-Session Memory

mimicode learns from previous sessions using **FTS5 full-text search**:

```bash
# Ask about past work
python agent.py "How did we previously handle authentication?"

# Agent searches:
#   - Past session messages
#   - Saved components and decisions
#   - Returns exact matches (no hallucinations)
```

**What gets stored:**
- Architectural decisions ("Why we chose ripgrep")
- Component summaries ("Router logic")
- Technical insights from past sessions

**What doesn't get stored:**
- Intermediate tool outputs
- Partial/truncated results
- Every message (too much noise)

**Why not embeddings?**
- Code has exact tokens (function names, file paths, error messages)
- Lexical search handles these perfectly
- No semantic drift or hallucinations
- Fast and predictable

---

## Terminal UI (TUI)

Launch the interactive terminal interface:

```bash
python agent.py --tui
```

**Features:**
- Line-by-line chat (like Claude.ai)
- Multi-line input support (Ctrl+Return to submit)
- Live session stats and cost tracking
- Color-coded output (user, bot, tools, errors)
- Session history and resumable sessions

**Keyboard shortcuts:**
- `Ctrl+C` — Interrupt agent
- `Ctrl+D` — Exit
- `Escape` — Clear input
- Tab — Auto-complete recent sessions

---

## Real Example: Rename Function

```
$ python agent.py -s example "Rename 'format_output' to 'stringify' everywhere"

[Session: example]

Turn 1: Agent (Sonnet) — Planning
  Message: "I'll help rename this function. Let me find all occurrences."
  
  Tool: bash → rg -l "format_output" --type py
  Result:
    utils.py
    main.py
    tests/test_utils.py

Turn 2: Agent (Haiku) — Edits
  Message: "Found 3 files. Updating each with surgical edits."
  
  Tool: read utils.py (lines 1–150)
  Tool: edit utils.py (batched: 4 edits)
    ✓ def format_output(): → def stringify():
    ✓ format_output(x) → stringify(x)
    ✓ docstring reference
    ✓ import statement
  
  Tool: edit main.py (1 edit)
  Tool: edit tests/test_utils.py (2 edits)

Turn 3: Agent (Haiku) — Verification
  Message: "Verifying the rename worked."
  
  Tool: bash → rg "format_output" --type py
  Result: (empty)
  
  ✓ Complete. Cost: $0.034
```

---

## Features Summary

| Feature | Benefit |
|---------|---------|
| **Four focused tools** | Predictable, auditable, fewer edge cases |
| **Exact text matching** | Prevents off-by-one errors in edits |
| **Atomic batch edits** | Partial failures impossible |
| **Ripgrep everywhere** | Fast, respects `.gitignore`, consistent |
| **Smart model routing** | 50–80% cost reduction vs. always Sonnet |
| **Session persistence** | Long-running projects stay organized |
| **Cross-session memory** | Learn from past work without hallucinations |
| **Full logging** | Every action timestamped and inspectable |
| **Prompt caching** | 20–30% token savings on multi-turn sessions |
| **Safety validation** | Blocks dangerous bash patterns |

---

## Limits (By Design)

- **Text files only** — No images, binaries, PDFs
- **No web access** — Can't fetch URLs (safety first)
- **One model per turn** — Can't switch mid-turn
- **Max 100KB output** — Forces focused searches
- **Max 2000 lines per read** — Encourages specificity

These limits make the agent more reliable, not less.

---

## Environment Variables

```bash
# Required
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional
export MIMICODE_CWD="/path/to/project"    # Default: current directory
export MIMICODE_MAX_STEPS="20"            # Max tools per turn (default: 15)
```

---

## How It Works Under the Hood

```
agent.py (main loop)
  ↓
  Classify intent → route_turn() → pick Haiku or Sonnet
  ↓
  Call Claude API (with prompt caching)
  ↓
  Agent uses tools (read, write, edit, bash)
  ↓
  Log all actions (logger.py) → sessions/<id>.jsonl
  ↓
  Save full conversation → sessions/<id>.messages.json
  ↓
  Index for memory search → .mimi/sessions.db (FTS5)
```

### File Organization

```
mimicode/
├── agent.py               # Main loop, CLI, session management
├── router.py              # Intent classification, model routing
├── tools.py               # The four tools + pre-flight validation
├── providers.py           # Claude API wrapper, prompt caching
├── memory_search.py       # FTS5 search over past sessions
├── mimi_memory.py         # Flat markdown memory, components
├── repomap.py             # AST-based repo structure extraction
├── logger.py              # JSONL event logging
├── tui.py                 # Terminal UI (Textual-based)
├── tools_router.py        # Routing analytics
├── check_deps.py          # Dependency validation
├── setup.sh               # Setup script
├── requirements.txt       # Python dependencies
├── ROUTING.md             # Routing documentation
├── sessions/              # Session storage
│   ├── <id>.jsonl        # Events
│   ├── <id>.messages.json # Full conversation
│   └── ...
├── bench/                 # Benchmarking suite
│   ├── runner.py
│   ├── tasks.py
│   ├── scorers.py
│   └── fixtures/          # Test tasks
└── tests/                 # Unit tests
```

---

## Testing

Run the full test suite:

```bash
pytest tests/
pytest tests/test_tools.py -v        # Test the four tools
pytest tests/test_router.py -v       # Test model routing
pytest tests/test_memory_search.py -v # Test memory system
```

Run benchmarks:

```bash
python bench/runner.py                      # Run all fixtures
python bench/runner.py --task search_basic  # Run one specific task
python bench/runner.py --model sonnet       # Override model
```

---

## Troubleshooting

### Ripgrep not found

```bash
rg --version
```

If missing, install it (see Quick Start above). Then:

```bash
python check_deps.py
```

### Agent seems stuck in a loop

Check the session log:

```bash
cat sessions/<id>.jsonl | tail -20
```

Look for repeated tool calls. You can interrupt with Ctrl+C.

### Output truncated at 100KB

Your search is too broad. Make it more specific:

```bash
# Too broad ❌
bash("rg 'def'")

# Better ✅
bash("rg 'def' src/ -t py")
```

### Models routing incorrectly

Force a specific model temporarily:

```bash
MIMICODE_MODEL=sonnet python agent.py "your prompt"
```

Session logs show every routing decision:

```bash
rg "model_route" sessions/<id>.jsonl
```

---

## Cost Examples

**Scenario: 10-turn coding session**

All Sonnet:
- 50K input tokens × $3/MTok = $0.15
- 10K output tokens × $15/MTok = $0.15
- **Total: $0.30**

With smart routing (70% Haiku):
- 7 Haiku turns: 35K input × $0.80/MTok + 7K output × $4/MTok = $0.056
- 3 Sonnet turns: 15K input × $3/MTok + 3K output × $15/MTok = $0.090
- **Total: $0.146**
- **Savings: 51%**

Typical workflows save 50–80% depending on task mix.

---

## Why This Design?

mimicode was built on an observation: **most coding tasks are execution, not planning.**

### The Problem

Traditional AI coding assistants give you everything (expensive, unfocused):
- Broad tool access → scope creep
- One model for all tasks → wastes money on simple operations
- No cross-session memory → repeat context constantly

### The Solution

**Deliberate constraint enables focus:**
- Fewer tools → fewer bugs → more predictable
- Ripgrep always → faster, consistent, respects `.gitignore`
- Smart routing → Sonnet for hard thinking, Haiku for simple work
- Persistent memory → cross-session knowledge without hallucinations

**Result:** Reliable, auditable, cost-effective.

---

## Philosophy

mimicode is built on these principles:

1. **Constraints enable focus.** Fewer tools = fewer edge cases.
2. **Explicit over implicit.** Code changes require exact text matches. No guessing.
3. **Predictable over surprising.** All tool calls are logged. No hidden operations.
4. **Cost-aware.** Smart routing means you pay less while maintaining quality.
5. **Learnable.** Read the code. It's small and straightforward.

---

## What's Next?

1. **Install dependencies** (5 minutes, see Quick Start)
2. **Run a task** — try `python agent.py --tui`
3. **Read the docs** — [ROUTING.md](ROUTING.md) explains the smart routing
4. **Explore sessions** — check `sessions/` to see what the agent saved
5. **Check the code** — it's 4–5 core files, very readable

---

## Contributing

This is a personal research project. Contributions welcome:

- **Bug reports:** Open an issue with session logs
- **Feature ideas:** Discuss before implementing (constraints are deliberate)
- **Benchmarks:** Run `python bench/runner.py` and share results

---

## License

Open source. Use it. Learn from it. Build with it.

**Last updated:** 2026-05-04

---

## FAQ

**Q: Why only four tools?**
A: Fewer tools = fewer bugs = more predictable behavior. These four handle 95% of real coding tasks.

**Q: Can I add more tools?**
A: You can modify `tools.py` and the agent's system prompt, but it violates the philosophy. Try to solve your problem with existing tools first.

**Q: Why ripgrep instead of grep?**
A: Ripgrep is ~10x faster and respects `.gitignore` by default. It prevents accidental scans of vendor directories.

**Q: Does the agent learn from my code?**
A: No, each session is isolated. But `memory_search` lets you query past sessions and share architectural decisions.

**Q: How much does it cost?**
A: Typical task: $0.02–$0.10 (Haiku-heavy). Complex refactoring: $0.10–$0.50 (more Sonnet). Always check session logs for exact costs.

**Q: Can I use it with other models?**
A: The code is built for Claude (Haiku + Sonnet). Adding other models requires significant changes.

**Q: Is my code safe?**
A: Sessions are stored locally (no cloud upload). All tool calls are validated before execution. Read `tools.py` for safety checks.

**Q: Can I pause and resume sessions?**
A: Yes! Use `-s sessionname` to create a named session. You can resume it anytime and pick up where you left off.

**Q: How do I analyze costs?**
A: Check `sessions/<id>.jsonl` for per-turn costs. Use `tools_session.py` for aggregate stats.
