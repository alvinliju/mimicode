# mimicode-tbench

Harbor adapter for running [mimicode](../) on Terminal-Bench 2.0.

## Install

```bash
uv tool install harbor
cd tbench_adapter
uv pip install -e .
```

## Smoke test

```bash
export ANTHROPIC_API_KEY=sk-ant-...
harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path mimicode_tbench:MimicodeAgent \
  -m anthropic/claude-haiku-4-5-20251001 \
  --task-ids hello-world
```

## Full run

```bash
harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path mimicode_tbench:MimicodeAgent \
  -m anthropic/claude-haiku-4-5-20251001 \
  --k 5 \
  --n-concurrent 4 \
  --jobs-dir ./tbench-runs/$(date +%Y%m%d-%H%M%S)
```

## Notes

- Anthropic provider only. Mimicode's `providers.py` doesn't speak others yet.
- Adapter sets `MIMICODE_MAX_STEPS=60` (mimicode's internal step counter, default 25). That's agent logic, not a Harbor resource override.
- Mimicode source is uploaded fresh per container; override location with `MIMICODE_SRC=/path/to/mimicode`.
