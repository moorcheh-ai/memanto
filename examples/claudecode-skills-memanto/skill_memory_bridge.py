"""
skill_memory_bridge.py
======================
A lightweight memory bridge that integrates Memanto's persistent memory layer
into mattpocock/skills-style developer workflows (Claude Code, /grill-with-docs,
/tdd, /handoff, etc.).

Architecture
------------
                 ┌─────────────────────────────────────────────────┐
                 │              Developer Skill Execution           │
                 │                                                  │
  before_skill() │  ┌──────────────┐    ┌──────────────────────┐  │
  ───────────────┼─►│ Query Memanto│    │  Inject memories as  │  │
                 │  │ for relevant │───►│  system constraints  │  │
                 │  │  memories    │    │  into skill prompt   │  │
                 │  └──────────────┘    └──────────────────────┘  │
                 │                                                  │
                 │         [Skill executes with context]           │
                 │                                                  │
  after_skill()  │  ┌──────────────┐    ┌──────────────────────┐  │
  ───────────────┼─►│ Distill key  │    │  Store to Memanto    │  │
                 │  │ learnings    │───►│  Engineering Profile  │  │
                 │  │ from output  │    │  (persistent memory)  │  │
                 │  └──────────────┘    └──────────────────────┘  │
                 └─────────────────────────────────────────────────┘

Two modes
---------
- LOCAL PREVIEW (default): Uses a JSONL file as a mock memory store.
  No API key required. Perfect for testing and CI.
- LIVE MEMANTO: Uses the real Memanto API via the `memanto` Python package.
  Requires a MOORCHEH_API_KEY environment variable.

Usage
-----
    from skill_memory_bridge import SkillMemoryBridge

    bridge = SkillMemoryBridge()  # auto-detects mode from env

    # Before running a skill
    context = bridge.before_skill("tdd", "Add rate limiting to the auth service")
    print(context)  # Prints relevant past memories to inject

    # After a skill completes
    bridge.after_skill("tdd", "Added token bucket rate limiter in auth/rate_limit.py")
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Memory:
    """A single memory entry in the Engineering Profile."""
    id: str
    skill: str
    content: str
    timestamp: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill": self.skill,
            "content": self.content,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        return cls(
            id=d["id"],
            skill=d["skill"],
            content=d["content"],
            timestamp=d["timestamp"],
            tags=d.get("tags", []),
        )


# ---------------------------------------------------------------------------
# Local preview backend (no API key required)
# ---------------------------------------------------------------------------

class LocalMemoryStore:
    """
    A JSONL-backed memory store for credential-free local preview.
    Each line in the JSONL file is a serialized Memory object.
    """

    def __init__(self, store_path: str = ".memanto_local.jsonl"):
        self.store_path = Path(store_path)
        self._memories: list[Memory] = []
        self._load()

    def _load(self) -> None:
        if self.store_path.exists():
            with open(self.store_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._memories.append(Memory.from_dict(json.loads(line)))
                        except (json.JSONDecodeError, KeyError):
                            pass

    def _save(self, memory: Memory) -> None:
        with open(self.store_path, "a") as f:
            f.write(json.dumps(memory.to_dict()) + "\n")
        self._memories.append(memory)

    def write(self, skill: str, content: str, tags: list[str] | None = None) -> Memory:
        # Combine ms timestamp with a short uuid4 suffix so rapid writes
        # within the same millisecond never collide on id.
        memory = Memory(
            id=f"local-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            skill=skill,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tags=tags or [skill],
        )
        self._save(memory)
        return memory

    def query(self, skill: str, query: str, limit: int = 5) -> list[Memory]:
        """
        Simple keyword-based retrieval for local mode.
        Returns memories most relevant to the current skill and query.
        """
        query_words = set(query.lower().split() + [skill.lower()])
        scored: list[tuple[float, Memory]] = []

        for mem in self._memories:
            mem_words = set(mem.content.lower().split())
            mem_tags = set(t.lower() for t in mem.tags)
            # Score: tag match (2pts each) + word overlap (1pt each)
            score = (
                2 * len(query_words & mem_tags)
                + len(query_words & mem_words)
            )
            if score > 0:
                scored.append((score, mem))

        scored.sort(key=lambda x: (-x[0], x[1].timestamp), reverse=False)
        return [m for _, m in scored[:limit]]

    def clear(self) -> None:
        """Remove all local memories (useful for testing)."""
        self._memories.clear()
        if self.store_path.exists():
            self.store_path.unlink()


# ---------------------------------------------------------------------------
# Live Memanto backend
# ---------------------------------------------------------------------------

class LiveMementoStore:
    """
    Wraps the official `memanto` Python package for live API access.
    Requires MOORCHEH_API_KEY in the environment.
    """

    def __init__(self, namespace: str = "developer-skills"):
        try:
            from memanto.cli.client.sdk_client import SDKClient  # type: ignore
        except ImportError as e:
            raise ImportError(
                "The `memanto` package is required for live mode. "
                "Install it with: pip install memanto"
            ) from e

        self.namespace = namespace
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "MOORCHEH_API_KEY is not set. "
                "Get a free key at https://console.moorcheh.ai/api-keys "
                "or use LOCAL_PREVIEW=true for credential-free mode."
            )
        self._client = SDKClient(api_key=api_key)

    def write(self, skill: str, content: str, tags: list[str] | None = None) -> dict:
        return self._client.add_memory(
            content=content,
            namespace=self.namespace,
            metadata={"skill": skill, "tags": tags or [skill]},
        )

    def query(self, skill: str, query: str, limit: int = 5) -> list[dict]:
        results = self._client.search_memories(
            query=f"[{skill}] {query}",
            namespace=self.namespace,
            limit=limit,
        )
        return results.get("memories", [])


# ---------------------------------------------------------------------------
# Main bridge
# ---------------------------------------------------------------------------

class SkillMemoryBridge:
    """
    The primary interface for integrating Memanto memory into developer skills.

    Auto-detects mode:
    - If MOORCHEH_API_KEY is set and LOCAL_PREVIEW != 'true': uses live Memanto API
    - Otherwise: uses local JSONL preview store

    Example
    -------
        bridge = SkillMemoryBridge()

        # Inject memories before a skill runs
        context = bridge.before_skill("tdd", "Add rate limiting to auth service")

        # Store learnings after a skill completes
        bridge.after_skill("tdd", "Used token bucket algorithm in auth/rate_limit.py")
    """

    def __init__(
        self,
        namespace: Optional[str] = None,
        local_store_path: str = ".memanto_local.jsonl",
        verbose: bool = True,
    ):
        self.verbose = verbose
        self._mode: str
        self._store: LocalMemoryStore | LiveMementoStore

        # Resolve namespace: explicit arg > MEMANTO_NAMESPACE env > default.
        # The .env.example and README advertise MEMANTO_NAMESPACE, so honor it.
        resolved_namespace = (
            namespace
            or os.environ.get("MEMANTO_NAMESPACE")
            or "developer-skills"
        )

        use_local = (
            os.environ.get("LOCAL_PREVIEW", "").lower() == "true"
            or not os.environ.get("MOORCHEH_API_KEY")
        )

        if use_local:
            self._store = LocalMemoryStore(store_path=local_store_path)
            self._mode = "local"
            if verbose:
                print("🔒 SkillMemoryBridge: LOCAL PREVIEW mode (no API key required)")
                print(f"   Memory store: {local_store_path}")
        else:
            self._store = LiveMementoStore(namespace=resolved_namespace)
            self._mode = "live"
            if verbose:
                print("🌐 SkillMemoryBridge: LIVE MEMANTO mode")
                print(f"   Namespace: {resolved_namespace}")

    @property
    def mode(self) -> str:
        return self._mode

    def before_skill(self, skill_name: str, task_description: str) -> str:
        """
        Called before a skill executes.
        Queries Memanto for relevant past memories and returns them as a
        formatted string to inject into the skill's system prompt.

        Parameters
        ----------
        skill_name : str
            The name of the skill being invoked (e.g., "tdd", "grill-with-docs").
        task_description : str
            A brief description of what the skill is about to do.

        Returns
        -------
        str
            A formatted block of relevant memories to inject as system constraints.
            Returns an empty string if no relevant memories are found.
        """
        if self.verbose:
            print(f"\n🧠 [before_skill:{skill_name}] Querying memory for: {task_description[:60]}...")

        memories = self._store.query(skill=skill_name, query=task_description)

        if not memories:
            if self.verbose:
                print("   No relevant memories found.")
            return ""

        lines = [
            f"## Engineering Profile — Relevant Past Context",
            f"The following memories from past skill executions are relevant to this task:",
            "",
        ]
        for i, mem in enumerate(memories, 1):
            if isinstance(mem, Memory):
                lines.append(f"{i}. [{mem.skill}] {mem.content}")
            else:
                # Live API returns dicts
                lines.append(f"{i}. {mem.get('content', str(mem))}")

        context = "\n".join(lines)
        if self.verbose:
            print(f"   Found {len(memories)} relevant memories.")
            print(f"   Context preview: {context[:120]}...")
        return context

    def after_skill(
        self,
        skill_name: str,
        summary: str,
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Called after a skill completes.
        Distills the key learnings from the skill output and stores them
        in Memanto to update the developer's Engineering Profile.

        Parameters
        ----------
        skill_name : str
            The name of the skill that just ran.
        summary : str
            A concise summary of what was done, decided, or learned.
        tags : list[str], optional
            Additional tags for better retrieval. Defaults to [skill_name].
        """
        if self.verbose:
            print(f"\n💾 [after_skill:{skill_name}] Storing memory: {summary[:60]}...")

        self._store.write(skill=skill_name, content=summary, tags=tags or [skill_name])

        if self.verbose:
            print("   Memory stored successfully.")

    def get_engineering_profile(self, limit: int = 20) -> list:
        """
        Returns all memories in the Engineering Profile (local mode only).
        Useful for debugging and validation.
        """
        if self._mode == "local":
            return [m.to_dict() for m in self._store._memories[-limit:]]
        else:
            return self._store.query(skill="*", query="engineering profile", limit=limit)
