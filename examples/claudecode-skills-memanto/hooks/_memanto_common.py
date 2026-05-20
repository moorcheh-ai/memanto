"""
Shared utilities for the Claude Code × Memanto hooks.

Centralizes:
- Memanto client instantiation (with sensible defaults from env)
- Project-scoped agent_id derivation
- Logging
- Graceful degradation (hooks must never crash the parent CLI)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# memanto and dotenv are imported lazily inside functions so a missing
# dependency degrades to a no-op instead of crashing Claude Code.


LOG_LEVEL = os.environ.get("MEMANTO_LOG_LEVEL", "INFO").upper()
LOG_DIR = Path.home() / ".claude" / "hooks" / "memanto" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to ~/.claude/hooks/memanto/logs/<name>.log."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(LOG_LEVEL)
    handler = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


@dataclass
class HookContext:
    """Parsed Claude Code hook invocation context."""
    payload: dict[str, Any]
    cwd: Path
    agent_id: str
    project_name: str


def derive_agent_id(cwd: Path) -> tuple[str, str]:
    """
    Return (agent_id, project_name).

    Honors MEMANTO_AGENT_ID env override (team-shared mode) and
    project-level .claude-memanto.json config.
    """
    # 1) Project-level override file
    config_path = cwd / ".claude-memanto.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(cfg.get("agent_id"), str) and cfg["agent_id"]:
                return cfg["agent_id"], cwd.name
        except (OSError, json.JSONDecodeError):
            pass  # fall through

    # 2) Env override
    env_override = os.environ.get("MEMANTO_AGENT_ID")
    if env_override:
        return env_override, cwd.name

    # 3) Project-scoped default
    digest = hashlib.sha256(str(cwd.resolve()).encode("utf-8")).hexdigest()[:10]
    safe_name = "".join(c for c in cwd.name.lower() if c.isalnum() or c == "-")[:30]
    return f"claude-code-{safe_name}-{digest}", cwd.name


def load_extra_tags(cwd: Path) -> list[str]:
    """Read `extra_tags` from a project-level `.claude-memanto.json` if present."""
    config_path = cwd / ".claude-memanto.json"
    if not config_path.exists():
        return []
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        tags = cfg.get("extra_tags", [])
        return [str(t) for t in tags if isinstance(t, str)]
    except (OSError, json.JSONDecodeError):
        return []


def parse_hook_input() -> HookContext | None:
    """
    Read Claude Code's hook JSON from stdin. Return None on parse failure.

    Claude Code hook stdin payload (schema):
        {
          "session_id": "...",
          "transcript_path": "/path/to/jsonl",
          "cwd": "/path/to/project",
          "hook_event_name": "Stop" | "UserPromptSubmit" | "PostToolUse",
          ... event-specific fields ...
        }
    """
    try:
        raw = sys.stdin.read()
        if not raw:
            return None
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None

    cwd_str = payload.get("cwd") or os.getcwd()
    cwd = Path(cwd_str).resolve()
    agent_id, project_name = derive_agent_id(cwd)

    return HookContext(
        payload=payload,
        cwd=cwd,
        agent_id=agent_id,
        project_name=project_name,
    )


def load_env() -> str | None:
    """Load .env from ~/.claude/hooks/memanto/ and return the MOORCHEH_API_KEY."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return os.environ.get("MOORCHEH_API_KEY")
    env_path = Path.home() / ".claude" / "hooks" / "memanto" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    return os.environ.get("MOORCHEH_API_KEY")


def make_client(api_key: str, agent_id: str, project_name: str):
    """
    Return a configured Memanto client + ensure the agent exists.

    Uses the `MemantoSetup` helper which handles agent creation and session
    bootstrapping. The first call for a given agent_id is slow (~1s) because
    it spins up a session; subsequent calls in the same hook invocation are
    fast.
    """
    # Late import: keeps hooks importable even without `memanto` installed
    from memanto.cli.client.sdk_client import SdkClient

    pattern = os.environ.get("MEMANTO_AGENT_PATTERN", "tool")
    auto_create = os.environ.get(
        "MEMANTO_AGENT_AUTO_CREATE", "true"
    ).lower() in ("1", "true", "yes")

    client = SdkClient(api_key=api_key)

    if auto_create:
        try:
            client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=f"Claude Code memory for project '{project_name}'",
            )
        except Exception:
            # Agent already exists or transient error — both are non-fatal here.
            pass

    return client


def safe_truncate(s: str, max_len: int) -> str:
    """Truncate a string to max_len, preserving readability with an ellipsis."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"
