#!/usr/bin/env python3
"""
Claude Code hook: UserPromptSubmit
==================================

On every user prompt, this hook queries Memanto for memories relevant to the
prompt and emits an `additional_context` JSON payload that Claude Code prepends
to the model's input — invisibly to the user but visible to Claude.

Failure modes are silent: missing API key, unreachable Memanto, parse errors —
all degrade to a no-op. A hook must NEVER block or crash Claude Code.

Wire-up in `~/.claude/settings.json`:
{
  "hooks": {
    "UserPromptSubmit": [
      {"matcher": "*", "hooks": [
        {"type": "command", "command": "python ~/.claude/hooks/memanto/inject_context.py"}
      ]}
    ]
  }
}
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Make sibling _memanto_common importable when the file is executed by Claude Code.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _memanto_common import (  # noqa: E402
    get_logger,
    load_env,
    make_client,
    parse_hook_input,
    safe_truncate,
)

LOG = get_logger("inject_context")

# Memory types that DON'T age out — preferences and architectural decisions
# stay relevant indefinitely.
TIMELESS_TYPES = {"preference", "decision", "instruction"}

# Memory age cutoff in days for all other types (events, observations, etc).
AGE_CUTOFF_DAYS = 90

DEFAULT_RECALL_LIMIT = int(os.environ.get("MEMANTO_RECALL_LIMIT", "5"))
DEFAULT_MIN_CONFIDENCE = float(os.environ.get("MEMANTO_MIN_CONFIDENCE", "0.6"))


def format_memory(mem: dict[str, Any]) -> str:
    """Render a single memory as a bullet for inclusion in the context block."""
    mtype = mem.get("type", "memory")
    title = safe_truncate(mem.get("title", "(no title)"), 80)
    content = safe_truncate(mem.get("content", ""), 300)
    confidence = mem.get("confidence", 0.0)
    tags = mem.get("tags") or []
    tag_str = f" [tags: {', '.join(tags[:3])}]" if tags else ""
    return (
        f"- ({mtype}, confidence={confidence:.2f}){tag_str}\n"
        f"  {title}\n"
        f"  → {content}"
    )


def filter_by_age(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop memories older than AGE_CUTOFF_DAYS, except for timeless types."""
    if not memories:
        return memories
    cutoff = datetime.now(timezone.utc) - timedelta(days=AGE_CUTOFF_DAYS)
    kept: list[dict[str, Any]] = []
    for mem in memories:
        if mem.get("type") in TIMELESS_TYPES:
            kept.append(mem)
            continue
        created = mem.get("created_at") or mem.get("createdAt")
        if not created:
            kept.append(mem)  # no timestamp → assume fresh
            continue
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            kept.append(mem)
            continue
        if ts >= cutoff:
            kept.append(mem)
    return kept


def build_context_block(memories: list[dict[str, Any]], project_name: str) -> str:
    """Produce the additional_context payload."""
    if not memories:
        return ""
    bullets = "\n".join(format_memory(m) for m in memories)
    return (
        f"## Memanto: relevant memory from past sessions in '{project_name}'\n"
        f"{bullets}\n\n"
        f"*These memories are auto-injected by Memanto based on your prompt's "
        f"relevance. Treat them as soft preferences from the developer/team — "
        f"prefer them over your defaults when they apply.*"
    )


def main() -> int:
    ctx = parse_hook_input()
    if ctx is None:
        LOG.debug("No hook input — exiting silently")
        return 0

    prompt = ctx.payload.get("prompt") or ctx.payload.get("user_prompt") or ""
    if not prompt or len(prompt) < 4:
        LOG.debug("Empty or trivial prompt — skipping")
        return 0

    api_key = load_env()
    if not api_key:
        LOG.warning("MOORCHEH_API_KEY not set — skipping injection")
        return 0

    try:
        client = make_client(api_key, ctx.agent_id, ctx.project_name)
    except Exception as exc:  # noqa: BLE001 - hook must never crash CLI
        LOG.error("Failed to instantiate Memanto client: %s", exc)
        return 0

    try:
        result = client.recall(
            agent_id=ctx.agent_id,
            query=prompt,
            limit=DEFAULT_RECALL_LIMIT,
            min_confidence=DEFAULT_MIN_CONFIDENCE,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.error("recall() failed: %s", exc)
        return 0

    memories = result.get("memories") or []
    LOG.info(
        "Recalled %d memories for prompt (truncated): %s",
        len(memories),
        safe_truncate(prompt, 80),
    )

    memories = filter_by_age(memories)
    if not memories:
        return 0

    context_block = build_context_block(memories, ctx.project_name)

    # Claude Code reads stdout as JSON when the hook emits an object with
    # `additional_context`. See https://docs.claude.com/en/docs/claude-code/hooks
    response = {"additional_context": context_block}
    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - last-resort safety net
        # Never raise out of a hook — Claude Code would block.
        LOG.exception("Unexpected error: %s", exc)
        sys.exit(0)
