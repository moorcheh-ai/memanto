"""
Claude Code Skills + Memanto Cross-Skill Memory Integration
==========================================================

Provides a global memory layer that survives across different
Claude Code skill executions, eliminating context fragmentation.

Key features:
- Pre-execution hook: inject past decisions into skill context
- Post-execution hook: extract learnings and store in Memanto
- Smart relevance matching for context injection
- Zero overhead when MOORCHEH_API_KEY is not set
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Memanto imports (optional; graceful fallback if not installed)
try:
    from memanto.cli.client.sdk_client import SdkClient
    HAS_MEMANTO = True
except ImportError:
    HAS_MEMANTO = False
    SdkClient = None  # type: ignore


@dataclass
class SkillContext:
    """Context passed to/from a skill execution."""
    skill_name: str
    skill_args: str = ""
    input_context: str = ""
    output_summary: str = ""
    file_paths: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class SkillMemory:
    """
    Cross-skill memory bridge powered by Memanto.

    Usage:
        mem = SkillMemory()
        mem.setup(developer_id="alice")

        # Before skill runs
        context = mem.pre_execute("grill-with-docs", file_paths=["src/main.py"])

        # Run skill...

        # After skill completes
        mem.post_execute(ctx, summary="Reviewed architecture, suggested factory pattern")
    """

    def __init__(self):
        self._client: Any = None
        self._developer_id: str = "default"
        self._agent_id: str = ""
        self._enabled: bool = False
        self._skill_history: list[SkillContext] = []

    def setup(
        self,
        developer_id: str,
        api_key: str | None = None,
    ) -> bool:
        """
        Initialize the Memanto client. Returns True if ready.

        Args:
            developer_id: Unique developer identifier (e.g. github username)
            api_key: Moorcheh API key. If None, reads from MOORCHEH_API_KEY env var.
        """
        if not HAS_MEMANTO:
            print("[SkillMemory] memanto package not installed. Run: pip install memanto")
            return False

        api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            print("[SkillMemory] MOORCHEH_API_KEY not set. Cross-skill memory disabled.")
            return False

        self._developer_id = developer_id
        self._agent_id = f"claudecode-skills-{developer_id}"

        try:
            self._client = SdkClient(api_key=api_key)
            self._client.create_agent(agent_id=self._agent_id, pattern="tool")
            self._client.activate_agent(self._agent_id, duration_hours=6)
            self._enabled = True
            print(f"[SkillMemory] Connected. Agent: {self._agent_id}")
            return True
        except Exception as e:
            print(f"[SkillMemory] Setup failed: {e}")
            return False

    def pre_execute(
        self,
        skill_name: str,
        file_paths: list[str] | None = None,
        skill_args: str = "",
    ) -> dict[str, Any]:
        """
        Called BEFORE a skill executes. Returns enriched context with
        relevant memories from past skill executions.

        Returns:
            dict with 'injected_context' (str) and 'raw_memories' (list)
        """
        ctx = SkillContext(
            skill_name=skill_name,
            skill_args=skill_args,
            file_paths=file_paths or [],
        )

        result: dict[str, Any] = {
            "injected_context": "",
            "raw_memories": [],
            "skill_context": ctx,
        }

        if not self._enabled:
            return result

        # Build a rich query for relevant memories
        query_parts = [f"skill:{skill_name}"]
        if file_paths:
            query_parts.append(f"files:{' '.join(file_paths[:3])}")
        if skill_args:
            query_parts.append(skill_args[:200])
        query = " ".join(query_parts)

        try:
            memories = self._client.recall(
                agent_id=self._agent_id,
                query=query,
                limit=8,
            ).get("memories", [])

            if memories:
                lines = ["## Cross-Skill Context (from past executions)"]
                for i, mem in enumerate(memories, 1):
                    mtype = mem.get("type", "fact")
                    lines.append(
                        f"{i}. [{mtype.upper()}] {mem.get('title', '')}: "
                        f"{mem.get('content', '')[:200]}"
                    )

                injected = "\n".join(lines)
                result["injected_context"] = injected
                result["raw_memories"] = memories

                print(
                    f"[SkillMemory] Injected {len(memories)} memories "
                    f"into {skill_name} context"
                )
            else:
                print(f"[SkillMemory] No relevant memories for {skill_name}")

        except Exception as e:
            print(f"[SkillMemory] Recall failed: {e}")

        return result

    def post_execute(
        self,
        ctx: SkillContext,
        summary: str,
        key_decisions: list[str] | None = None,
        code_patterns: list[str] | None = None,
    ) -> bool:
        """
        Called AFTER a skill completes. Extracts learnings and stores them
        in Memanto for future skill sessions.

        Args:
            ctx: The SkillContext from pre_execute
            summary: Brief description of what happened
            key_decisions: Architectural/design decisions made
            code_patterns: Patterns/conventions used or discovered

        Returns:
            True if memories were stored successfully
        """
        if not self._enabled:
            return False

        ctx.output_summary = summary
        self._skill_history.append(ctx)

        stored_count = 0

        # 1. Store the skill execution event
        try:
            self._client.remember(
                agent_id=self._agent_id,
                memory_type="event",
                title=f"Skill: {ctx.skill_name}",
                content=(
                    f"Executed skill '{ctx.skill_name}' with args: {ctx.skill_args}\n"
                    f"Files: {', '.join(ctx.file_paths[:5])}\n"
                    f"Summary: {summary[:800]}"
                ),
                confidence=0.9,
                tags=["claudecode-skill", ctx.skill_name, "execution"],
            )
            stored_count += 1
        except Exception as e:
            print(f"[SkillMemory] Failed to store event: {e}")

        # 2. Store key decisions as high-confidence memories
        for decision in (key_decisions or []):
            try:
                self._client.remember(
                    agent_id=self._agent_id,
                    memory_type="decision",
                    title=f"Decision from {ctx.skill_name}",
                    content=decision[:800],
                    confidence=0.85,
                    tags=["decision", "architecture", ctx.skill_name],
                )
                stored_count += 1
            except Exception:
                pass

        # 3. Store code patterns/conventions
        for pattern in (code_patterns or []):
            try:
                self._client.remember(
                    agent_id=self._agent_id,
                    memory_type="instruction",
                    title=f"Convention from {ctx.skill_name}",
                    content=pattern[:800],
                    confidence=0.8,
                    tags=["convention", "pattern", ctx.skill_name],
                )
                stored_count += 1
            except Exception:
                pass

        print(f"[SkillMemory] Stored {stored_count} memories from {ctx.skill_name}")
        return stored_count > 0

    def recall_recent(
        self,
        query: str = "",
        limit: int = 10,
    ) -> list[dict]:
        """Query Memanto for recent memories across all skills."""
        if not self._enabled:
            return self._in_memory_recall(query, limit)

        try:
            result = self._client.recall(
                agent_id=self._agent_id,
                query=query or "recent skill executions",
                limit=limit,
            )
            return result.get("memories", [])
        except Exception as e:
            print(f"[SkillMemory] Recall failed: {e}")
            return []

    def get_cross_skill_context(self, skill_name: str) -> str:
        """
        Generate a consolidated context string from all past skills.
        This is the key value proposition: zero repeated instructions.
        """
        memories = self.recall_recent(f"skill:{skill_name} OR architecture OR convention", limit=12)
        if not memories:
            return ""

        lines = [
            "## Cross-Skill Knowledge",
            "The following was learned from previous skill executions:",
        ]
        for mem in memories:
            lines.append(f"- [{mem.get('type', '?')}] {mem.get('title', '')}: {mem.get('content', '')[:150]}")
        return "\n".join(lines)

    # -- GIT-based quick reference (works without Moorcheh) --

    def last_commit_summary(self, repo_path: str = ".") -> str:
        """Get the last git commit message as a quick context snapshot."""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "log", "-1", "--oneline", "--no-decorate"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def recent_branches(self, repo_path: str = ".", count: int = 5) -> list[str]:
        """Get recently modified branches for context awareness."""
        try:
            result = subprocess.run(
                [
                    "git", "-C", repo_path, "branch", "--sort=-committerdate",
                    "--format=%(refname:short) %(committerdate:relative)",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return [line for line in result.stdout.strip().split("\n")[:count] if line]
        except Exception:
            return []

    def _in_memory_recall(self, query: str, limit: int) -> list[dict]:
        """Fallback: search recent skill history in-memory when Memanto is unavailable."""
        results = []
        for ctx in self._skill_history[-limit:]:
            if query.lower() in ctx.output_summary.lower() or query.lower() in ctx.skill_name.lower():
                results.append({
                    "type": "event",
                    "title": ctx.skill_name,
                    "content": ctx.output_summary[:200],
                })
        return results


# ---------------------------------------------------------------------------
# Hook utilities for integration with Claude Code skill lifecycle
# ---------------------------------------------------------------------------

HOOK_TEMPLATE = """#!/usr/bin/env python3
\"\"\"Pre-execution hook for '{skill_name}' skill.\"\"\"
import json, sys, os

# Add the claudecode-skills-memanto package to path
sys.path.insert(0, os.path.dirname(__file__))

from skill_memory import SkillMemory

mem = SkillMemory()
mem.setup(developer_id=os.environ.get("DEVELOPER_ID", "unknown"))

input_data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
file_paths = input_data.get("files", [])

ctx = mem.pre_execute(
    skill_name="{skill_name}",
    file_paths=file_paths,
)

if ctx["injected_context"]:
    print(ctx["injected_context"])
else:
    print("")
"""


def generate_hooks(skill_names: list[str], output_dir: str = ".") -> None:
    """
    Generate pre-execution hook scripts for a list of skill names.

    Usage:
        from skill_memory import generate_hooks
        generate_hooks(["grill-with-docs", "tdd", "handoff"], output_dir="hooks/")
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name in skill_names:
        script = HOOK_TEMPLATE.format(skill_name=name)
        hook_path = out / f"pre_{name.replace('-', '_')}.py"
        hook_path.write_text(script, encoding="utf-8")
        print(f"Generated: {hook_path}")
