# Smart Model Routing

Mimicode automatically routes requests to **Haiku 3.5** or **Sonnet 4.5** based on task complexity. This reduces costs by ~60-80% while maintaining quality for most operations.

## Why Routing Matters

**Cost difference (May 2026):**
- **Haiku 3.5**: $0.80/MTok input, $4/MTok output (5x cheaper)
- **Sonnet 4.5**: $3/MTok input, $15/MTok output (smarter, slower)

**Key insight:** Most coding tasks are **execution**, not planning. With strong prompt guidance, Haiku can handle:
- File reading and searching
- Simple single-file edits
- Running tests/commands
- Straightforward refactors

Sonnet is reserved for:
- Initial planning (first turn)
- Multi-file changes
- Complex debugging
- Ambiguous requirements

## Routing Rules

### ✅ Haiku (Fast & Cheap)

**Read-only operations:**
```
"Where is the bash function?"
"Show me all imports in agent.py"
"Find references to 'route_model'"
```

**Simple edits (single file):**
```
"Change VERSION to 0.2 in config.py"
"Rename foo to bar in helpers.py only"
"Fix typo in README.md"
```

**Bash commands:**
```
"Run pytest and show results"
"Install requirements"
"Build the project"
```

### 🧠 Sonnet (Smart & Careful)

**First turn (planning):**
- Always uses Sonnet to understand the task

**Multi-file changes:**
```
"Rename variable foo to bar everywhere"
"Update imports across the entire codebase"
"Refactor architecture for X"
```

**Debugging:**
- After tool errors → switches to Sonnet
- Complex error traces
- Performance issues

**Complex planning:**
```
"What's the best approach to add feature X?"
"Design a new module for Y"
"Explain the architecture"
```

## Extra Guidance for Haiku

When routing to Haiku, mimicode adds **task-specific guidance** to the system prompt:

**For edits:**
> Read the file first. Use exact old_text matching with 2-3 lines context. For multiple edits in one file, use batched edits=[...]. Double-check uniqueness.

**For searches:**
> Use `rg` for searches. Be precise and quote file:line.

**For bash:**
> Run commands directly. Show output. Be concise.

This **scaffolding** lets Haiku perform at near-Sonnet quality for scoped tasks.

## Monitoring Routing

### In TUI

Use the `/route` slash command:

```
/route
```

Output:
```
Total routing decisions: 12
Haiku usage: 66.7%

By model:
  haiku-3.5      8 ( 66.7%)
  sonnet-4.5     4 ( 33.3%)

By reason:
  first_turn             2 ( 16.7%)
  simple_edit            5 ( 41.7%)
  simple_read            3 ( 25.0%)
  fallback               2 ( 16.7%)
```

### In Session Logs

Check `sessions/<id>.jsonl` for `model_route` events:

```json
{
  "kind": "model_route",
  "data": {
    "step": 2,
    "model": "claude-3-5-haiku-20250312",
    "reason": "simple_edit",
    "has_guidance": true
  }
}
```

## Cost Savings Example

**Typical session without routing (all Sonnet):**
- 10 turns, 50K tokens input, 10K tokens output
- Cost: (50K × $3/M) + (10K × $15/M) = $0.30

**Same session with routing (70% Haiku):**
- 7 turns Haiku: (35K × $0.80/M) + (7K × $4/M) = $0.056
- 3 turns Sonnet: (15K × $3/M) + (3K × $15/M) = $0.090
- **Total: $0.146 (51% savings)**

Real savings depend on your workflow. Heavy refactors → more Sonnet. Quick edits/searches → more Haiku.

## Philosophy

This isn't about replacing engineers with cheaper models. It's about **matching tool to task**:

- **Haiku** for well-defined execution (reading, simple edits, tests)
- **Sonnet** for ambiguous planning, reasoning, complex changes

You stay in control. The router just picks the right wrench for each bolt.

## Tuning (Advanced)

Edit `router.py` to customize routing rules:

```python
# Make routing more aggressive (use Haiku more)
if "refactor" in content_lower and "simple" in content_lower:
    return HAIKU_3_5, "simple_edit", guidance

# Make routing more conservative (use Sonnet more)
if "production" in content_lower or "critical" in content_lower:
    return SONNET_4_5, "safety", ""
```

Test changes with:
```bash
pytest tests/test_router.py -v
```

## Disabling Routing

To force Sonnet for everything (no routing), set an environment variable:

```bash
export MIMICODE_FORCE_SONNET=1
python agent.py --tui
```

*(Not implemented yet — coming soon if needed)*
