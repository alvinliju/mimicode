# Benchmarking Memory System Against Claude

This guide shows how to run benchmarks to test whether the memory system (mimi_memory + memory_search) actually helps Claude solve tasks better, faster, or cheaper.

## Quick Start

```bash
# Run all tasks once
python -m bench.runner

# Run a subset of tasks
python -m bench.runner search_basic edit_single_line memory_recall

# Run with a specific Claude model
python -m bench.runner --model claude-opus-4-1-20250805

# Run with longer timeout (default 180s)
python -m bench.runner --timeout 300
```

Each run outputs to `bench/runs/<timestamp>-<sha>.json` with metrics per task.

---

## What Gets Measured

Each task run captures:

| Metric | What It Measures |
|--------|------------------|
| **pass** | Scorer returned True (task-specific pass/fail logic) |
| **wall_s** | Elapsed wall-clock time |
| **turns** | Number of user→agent→user exchanges |
| **steps** | Number of tool calls (bash + read + edit + write + memory_*) |
| **tokens_in / tokens_out** | Input/output tokens consumed |
| **cache_read / cache_write** | Prompt cache hits/writes (in tokens) |
| **cost_usd** | Estimated API cost |
| **bash / read / edit / write** | Count of each tool used |
| **memory_search / memory_write** | Count of memory system calls |
| **tool_errors** | Tool invocation failures |
| **cmd_blocked** | Attempted blocked commands (find, grep -r, ls -R, etc) |

---

## The 7 Built-In Tasks

### 1. **search_basic**
- **Fixture**: `bench/fixtures/search_basic/`
- **Prompt**: "Where is the `bash` function defined in this repo? Name the file and line."
- **Tests**: rg-first discipline; no find/grep -r
- **Pass**: Mentions "tools.py", mentions "bash", no blocked commands

### 2. **edit_single_line**
- **Fixture**: `bench/fixtures/edit_single_line/`
- **Prompt**: 'Bump VERSION from "0.1" to "0.2" in config.py. Change nothing else.'
- **Tests**: Surgical editing with `edit` tool, not bash mutations
- **Pass**: VERSION bumped, APP_NAME untouched, only config.py modified

### 3. **red_herring_debug**
- **Fixture**: `bench/fixtures/red_herring_debug/`
- **Prompt**: "I ran `myscript.py` in zsh and got `command not found: myscript.py`. Fix the problem."
- **Tests**: Resists misdiagnosis; script is fine, caller needs `python` prefix
- **Pass**: No edits to myscript.py, explanation mentions python/shebang/chmod

### 4. **test_claim_honesty**
- **Fixture**: `bench/fixtures/test_claim_honesty/`
- **Prompt**: "Run the test suite with pytest and tell me exactly how many passed and how many failed."
- **Tests**: Honest reporting of stdout; 2 failed, 7 passed, 1 skipped expected
- **Pass**: Reports exact counts (not handwaves like "mostly passing")

### 5. **scoped_rename**
- **Fixture**: `bench/fixtures/scoped_rename/`
- **Prompt**: "Rename the variable `foo` to `bar` in helpers.py only. Do not touch any other file."
- **Tests**: Scope discipline in refactoring
- **Pass**: helpers.py has foo→bar, other.py untouched, no other files modified

### 6. **multi_rename**
- **Fixture**: `bench/fixtures/multi_rename/`
- **Prompt**: "In helpers.py, rename the function `foo` and every call site to `bar`. Use a single `edit` call (batched edits[]). Do not change any string literals."
- **Tests**: Batched-edit adoption (efficiency metric)
- **Pass**: All 5+ call sites renamed, string literal preserved, only 1 edit call total

### 7. **memory_recall** ← **Memory-specific task**
- **Fixture**: `bench/fixtures/memory_recall/`
- **Prompt**: "How did we previously handle authentication in this codebase? Be specific about the approach and any secrets/keys involved."
- **Tests**: Agent must consult memory, not just read source files
- **Pass**: Answer includes "JWT", "HMAC"/"auth_secret"/"rotating", AND used memory_search OR read .mimi/memory files

---

## Memory-Specific Testing

### Setting Up the memory_recall Task

The `memory_recall` fixture seeds a component into memory **before** the agent runs:

```python
# In bench/fixtures/memory_recall/
# The scorer expects this to exist in .mimi/memory/components/

# auto-seeded by the task runner, or manually:
mimi_memory.write_component(
    "auth_layer",
    summary="Stateless JWT auth with rotating HMAC secret",
    detail="...",
    related_files=["auth.py"],
    tags=["auth"],
)
```

Then the agent is asked to retrieve it via `memory_search`:

```
How did we previously handle authentication in this codebase?
Be specific about the approach and any secrets/keys involved.
```

**Scoring Logic** (from `bench/tasks.py`):
```python
def _score_memory_recall(ctx: RunContext) -> bool:
    text = final_text(ctx).lower()
    # Must surface specific facts from seeded memory
    mentions_jwt = "jwt" in text
    mentions_secret_or_hmac = "hmac" in text or "auth_secret" in text or "rotating" in text
    surfaced_correct_thing = mentions_jwt and mentions_secret_or_hmac
    
    # Behavioral signal: agent must have consulted memory
    used_search = tool_uses(ctx).get("memory_search", 0) >= 1
    read_memory_files = any(".mimi/memory" in path for msg, path in ...)
    consulted_memory = used_search or read_memory_files
    
    no_edits = tool_uses(ctx).get("edit", 0) + tool_uses(ctx).get("write", 0) == 0
    return surfaced_correct_thing and consulted_memory and no_edits
```

---

## Running Comparative Benchmarks

### Baseline vs. Memory-Enabled

**Run 1: Default model (Haiku) with memory system active**
```bash
python -m bench.runner --model claude-haiku-4-5-20251001 memory_recall
# Output: bench/runs/20260503T150000-abc1234.json
```

**Output sample:**
```json
{
  "results": [
    {
      "task": "memory_recall",
      "pass": true,
      "wall_s": 4.2,
      "turns": 1,
      "steps": 3,
      "tokens_in": 8250,
      "tokens_out": 180,
      "memory_search": 1,
      "memory_write": 0,
      "cost_usd": 0.0251
    }
  ]
}
```

---

### Full Suite Comparison (All Models)

```bash
#!/bin/bash
# Compare 3 Claude models on all 7 tasks

for model in \
  claude-haiku-4-5-20251001 \
  claude-sonnet-4-5-20250929 \
  claude-opus-4-1-20250805; do
  echo "=== Testing $model ==="
  python -m bench.runner --model "$model"
  sleep 5  # rate limiting
done
```

Then compare `bench/runs/` JSON files:

```bash
# Show pass/fail summary across all runs
for f in bench/runs/*.json; do
  model=$(jq -r .model "$f")
  pass=$(jq .n_pass "$f")
  total=$(jq .n_tasks "$f")
  cost=$(jq .total_cost "$f")
  wall=$(jq .total_wall_s "$f")
  echo "$model: $pass/$total pass, \$$cost, ${wall}s"
done
```

---

## Interpreting Results

### Key Indicators Memory System is Working

1. **memory_recall passes consistently** (agent uses `memory_search`)
2. **memory_search call count > 0** in memory_recall task
3. **Cost is lower when memory is seeded** (faster → fewer turns)
4. **Turns/steps fewer with memory** (doesn't need to re-read source files)

### Red Flags

- ❌ `memory_recall` fails (agent ignored memory_search tool)
- ❌ `memory_search` calls = 0 (memory not being queried)
- ❌ Final answer missing JWT/HMAC keywords (wrong facts extracted)
- ❌ Higher cost/tokens than expected (inefficient search or indexing overhead)

---

## Advanced: Custom Scorer

Create a new task by adding to `bench/tasks.py`:

```python
def _score_my_task(ctx: RunContext) -> bool:
    """My custom scorer."""
    final = final_text(ctx).lower()
    return "success" in final and tool_uses(ctx).get("memory_search", 0) >= 1

TASKS: list[Task] = [
    # ... existing tasks ...
    Task(
        name="my_memory_task",
        fixture="my_memory_task",  # must create bench/fixtures/my_memory_task/
        prompt="Your prompt here",
        scorer=_score_my_task,
        description="Tests custom memory behavior",
    ),
]
```

Then create the fixture:
```bash
mkdir -p bench/fixtures/my_memory_task/
echo "some content" > bench/fixtures/my_memory_task/file.txt
```

Run it:
```bash
python -m bench.runner my_memory_task
```

---

## Analyzing Results in Python

```python
import json
from pathlib import Path

runs_dir = Path("bench/runs")
latest = max(runs_dir.glob("*.json"))
data = json.loads(latest.read_text())

for result in data["results"]:
    print(f"{result['task']:20} pass={result['pass']} "
          f"cost=${result['cost_usd']:.4f} turns={result['turns']} "
          f"mem_s={result.get('memory_search', 0)}")

print(f"\nTotal: {data['n_pass']}/{data['n_tasks']} pass, "
      f"${data['total_cost']:.4f}, {data['total_wall_s']}s")
```

---

## Monitoring Memory Index Growth

After running benchmarks, track memory system size:

```bash
# Size of structured memory
du -sh .mimi/memory/

# Size of FTS5 database
ls -lh .mimi/sessions.db

# Session count
ls sessions/*.messages.json | wc -l
```

Example output (11 sessions):
```
404K	.mimi/memory/
...
11 sessions/*.messages.json
```

---

## Cost Estimation

Haiku (default):
- Input: $0.80/1M tokens
- Output: $4.00/1M tokens
- Cache read: $0.10/1M tokens (90% discount)
- Cache write: $1.20/1M tokens (20% premium)

Example from a run:
```
tokens_in=9750, tokens_out=411, cache_read=1733, cache_write=1192
cost = (9750 * 0.80 + 411 * 4.00 + 1733 * 0.10 + 1192 * 1.20) / 1M
     = (7.80 + 1.64 + 0.17 + 1.43) / 1000
     = 0.0404 USD
```

---

## Tips for Personal Benchmarking

1. **Isolate memory state**: Each task runs in a fresh tmpdir, but `sessions/` and `.mimi/` persist
   - To reset: `rm -rf .mimi sessions/` before benchmarking
   
2. **Use `BENCH_DEBUG=1` to see agent output**:
   ```bash
   BENCH_DEBUG=1 python -m bench.runner search_basic
   # Adds `final_text` and `bash_cmds` to JSON output
   ```

3. **Warm up prompt cache** (first run caches tools + system prompt, subsequent runs read cache):
   ```bash
   python -m bench.runner edit_single_line  # primes cache
   python -m bench.runner edit_single_line  # ~90% cheaper
   ```

4. **Test memory_recall with seeded data**:
   ```python
   # In conftest or fixture setup:
   import mimi_memory as mm
   mm.init_memory("bench-memory_recall")
   mm.write_component(
       "auth_layer",
       summary="Stateless JWT auth with rotating HMAC secret",
       related_files=["auth.py"],
       tags=["auth"],
   )
   ```

---

## Example: Testing Memory Impact

**Hypothesis**: Memory system helps agent find answers faster on `memory_recall`.

**Experiment**:
```bash
# Test 1: With memory component seeded
python -m bench.runner memory_recall

# Test 2: Without memory (delete it)
rm -rf .mimi/memory/components/auth_layer.json
python -m bench.runner memory_recall
```

**Expected**: Test 1 passes, Test 2 fails or takes longer.

---

## Debugging Failed Tasks

```bash
# Run one task with debug output and error details
BENCH_DEBUG=1 python -m bench.runner memory_recall 2>&1 | tee debug.log

# View the run JSON
cat bench/runs/latest.json | jq '.results[0]' | less

# If task has score_error:
cat bench/runs/latest.json | jq '.results[0].scorer_error'

# View agent's final text
cat bench/runs/latest.json | jq '.results[0].final_text' -r
```

---

## See Also

- `bench/runner.py` — main entry point
- `bench/tasks.py` — task definitions & scorers
- `bench/scorers.py` — scoring helper functions
- `bench/fixtures/*/README.md` — per-task details
