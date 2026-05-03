"""
Harbor adapter for mimicode on Terminal-Bench 2.0.

Run with:
    harbor run -d terminal-bench@2.0 \\
        --agent-import-path mimicode_tbench:MimicodeAgent \\
        -m anthropic/claude-haiku-4-5-20251001 \\
        --task-ids hello-world

The adapter does three things:
  1. install():  sets up python + ripgrep + anthropic SDK in the task container
                 and uploads the local mimicode source tree to /opt/mimicode.
  2. run():      invokes `python agent.py "<instruction>"` inside the container
                 with MIMICODE_MODEL pinned to whatever Harbor passed via -m.
  3. populate_context_post_run(): parses mimicode's JSONL session log to
                 surface token usage / cost back to Harbor.

Source-tree resolution (where to find mimicode/ on the host):
  - Env var MIMICODE_SRC if set,
  - else this file's grandparent (assumes adapter sits at
    <mimicode>/tbench_adapter/mimicode_tbench/agent.py).
"""

import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

# Anything matching these patterns is excluded from the upload to the task
# container. .venv alone is ~300MB on a typical dev machine — leaving it in
# pushes setup past Harbor's 10-min AgentSetupTimeout.
_UPLOAD_EXCLUDES = (
    # Heavy / stale
    ".venv",
    ".mimi",
    ".git",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".ruff_cache",
    "tbench-runs",
    "tbench_adapter",
    "bench/runs",
    "node_modules",
    ".DS_Store",
    "sessions",  # old per-session logs, not needed at runtime
    "tmp",
    # Secrets — never ship these into a container
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
)


def _mimicode_src() -> Path:
    """Locate the mimicode source root on the host filesystem."""
    override = os.environ.get("MIMICODE_SRC")
    if override:
        p = Path(override).expanduser().resolve()
        if not (p / "agent.py").is_file():
            raise FileNotFoundError(
                f"MIMICODE_SRC={p} does not contain agent.py"
            )
        return p
    # adapter lives at <repo>/tbench_adapter/mimicode_tbench/agent.py
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "agent.py").is_file():
        return candidate
    raise FileNotFoundError(
        "Cannot locate mimicode source. Set MIMICODE_SRC=/path/to/mimicode."
    )


class MimicodeAgent(BaseInstalledAgent):
    _LOG_FILENAME = "mimicode.log"
    _SESSION_LOG = "mimicode-session.jsonl"

    @staticmethod
    def name() -> str:
        return "mimicode"

    def get_version_command(self) -> str | None:
        return "cat /opt/mimicode/VERSION 2>/dev/null || echo dev"

    async def install(self, environment: BaseEnvironment) -> None:
        # Harbor's agent setup budget is 360s. Under --n-concurrent N, that
        # 360s is wall-clock per container while N containers are doing the
        # same apt-get/pip dance. We detect-then-install instead of unconditional
        # apt-get update (which alone can take 60s per container under load).
        await self.exec_as_root(
            environment,
            command=(
                "set -e; "
                # python3 + pip: only install if missing. Most tbench base
                # images are Debian bookworm and already ship python3.
                "if ! command -v python3 >/dev/null || ! command -v pip3 >/dev/null; then "
                "  apt-get update -qq && "
                "  apt-get install -y --no-install-recommends python3 python3-pip ca-certificates curl; "
                "fi; "
                # ripgrep: try apt first, else fall back to a static prebuilt
                # binary from upstream. Static binary is one file, ~5MB —
                # faster than apt under contention.
                "if ! command -v rg >/dev/null; then "
                "  apt-get install -y --no-install-recommends ripgrep 2>/dev/null || "
                "  (apt-get install -y --no-install-recommends curl ca-certificates xz-utils 2>/dev/null; "
                "   curl -fsSL https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep-14.1.0-x86_64-unknown-linux-musl.tar.gz "
                "     -o /tmp/rg.tar.gz && "
                "   tar -xzf /tmp/rg.tar.gz -C /tmp && "
                "   cp /tmp/ripgrep-*/rg /usr/local/bin/rg && "
                "   chmod +x /usr/local/bin/rg); "
                "fi"
            ),
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )

        # Stage and upload mimicode source. Filtered to ~300KB so this is fast.
        src = _mimicode_src()
        await self.exec_as_root(
            environment,
            command="mkdir -p /opt/mimicode && chown -R $(id -u):$(id -g) /opt/mimicode || true",
        )

        with tempfile.TemporaryDirectory(prefix="mimicode-stage-") as stage:
            stage_root = Path(stage) / "mimicode"
            shutil.copytree(
                src,
                stage_root,
                ignore=shutil.ignore_patterns(*_UPLOAD_EXCLUDES),
            )
            await environment.upload_dir(stage_root, "/opt/mimicode")

        # Install anthropic SDK into user-site (no venv, no upgrade pip).
        # PEP 668 marks system Python as externally-managed on bookworm; the
        # --break-system-packages flag is the documented escape hatch for
        # ephemeral containers. Fallback for older pip versions that don't
        # know the flag.
        await self.exec_as_agent(
            environment,
            command=(
                "set -e; "
                "pip3 install --user --no-cache-dir --break-system-packages 'anthropic>=0.40' 2>/dev/null || "
                "pip3 install --user --no-cache-dir 'anthropic>=0.40'; "
                "python3 -c 'import anthropic; print(\"anthropic\", anthropic.__version__)'; "
                "rg --version | head -1"
            ),
        )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError(
                "MimicodeAgent requires -m <provider/model>, e.g. "
                "anthropic/claude-haiku-4-5-20251001"
            )

        # Mimicode currently only speaks Anthropic. Fail loudly on anything
        # else rather than silently mis-routing.
        provider, _, model = self.model_name.partition("/")
        if not model:
            # No provider prefix — assume anthropic.
            provider, model = "anthropic", provider
        if provider != "anthropic":
            raise ValueError(
                f"MimicodeAgent only supports anthropic provider; got {provider!r}. "
                "Pass -m anthropic/<model>."
            )

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set on host")

        env = {
            "ANTHROPIC_API_KEY": api_key,
            # Pin the exact model Harbor asked for; bypass mimicode's own router.
            "MIMICODE_MODEL": model,
            # Bump step budget for tbench-style multi-tool tasks. Mimicode's
            # default of 25 is fine for single-file edits but tbench tasks
            # routinely need 40-60 tool calls. This is internal agent logic,
            # not a Harbor timeout/resource override.
            "MIMICODE_MAX_STEPS": os.environ.get("MIMICODE_MAX_STEPS", "60"),
        }

        escaped = shlex.quote(instruction)
        log_path = f"/logs/agent/{self._LOG_FILENAME}"

        # Run mimicode FROM the task's working directory (typically /app on
        # tbench), not from /opt/mimicode. This matters because:
        #   - mimicode's tools (bash/read/edit/write) use cwd-relative paths
        #   - build_repo_map(cwd) scans cwd; if cwd were /opt/mimicode it
        #     would index mimicode's own source instead of the task files,
        #     wasting tokens and confusing the model
        #   - .mimi/ and sessions/ are written under cwd
        # We `cd /app || cd ~` for robustness if a future task uses a
        # different convention.
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "mkdir -p /logs/agent; "
                "cd /app 2>/dev/null || cd \"$HOME\"; "
                "TASK_CWD=$(pwd); "
                f"python3 /opt/mimicode/agent.py -s tbench {escaped} 2>&1 | "
                f"stdbuf -oL tee {log_path} || true; "
                # surface mimicode's structured session log (best-effort).
                f"cp -f \"$TASK_CWD/sessions/tbench.jsonl\" "
                f"/logs/agent/{self._SESSION_LOG} 2>/dev/null || true"
            ),
            env=env,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Sum token usage from mimicode's per-step model_response events."""
        log_file = self.logs_dir / self._SESSION_LOG
        if not log_file.exists():
            return

        n_input = 0
        n_output = 0
        n_cache_read = 0
        n_cache_write = 0
        cost_usd = 0.0

        # Pricing fallbacks — only used if mimicode didn't already log a cost.
        # Keep in sync with bench/scorers.py PRICING.
        PRICING = {
            "claude-haiku-4-5-20251001":   (1.00, 5.00, 0.10, 1.25),
            "claude-sonnet-4-5":           (3.00, 15.00, 0.30, 3.75),
            "claude-sonnet-4-5-20250929":  (3.00, 15.00, 0.30, 3.75),
        }

        for line in log_file.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") not in ("model_response", "model_response_streaming"):
                continue
            data = ev.get("data") or {}
            inp = int(data.get("input_tokens") or 0)
            out = int(data.get("output_tokens") or 0)
            cr = int(data.get("cache_read_input_tokens") or 0)
            cw = int(data.get("cache_creation_input_tokens") or 0)
            n_input += inp
            n_output += out
            n_cache_read += cr
            n_cache_write += cw

            model = data.get("model") or ""
            rates = PRICING.get(model)
            if rates:
                in_r, out_r, cr_r, cw_r = rates
                cost_usd += (
                    inp * in_r + out * out_r + cr * cr_r + cw * cw_r
                ) / 1_000_000

        context.n_input_tokens = n_input + n_cache_read
        context.n_output_tokens = n_output
        context.n_cache_tokens = n_cache_read
        context.cost_usd = cost_usd if cost_usd > 0 else None
