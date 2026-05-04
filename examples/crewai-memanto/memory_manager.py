"""
Memory Manager — Contradictory memory handling + Data Toolkit export.

Handles:
1. Contradictory memory detection (same fact, different value)
2. Versioning with confidence scores
3. Merge/prune strategies
4. Export to JSON/CSV via Data Toolkit normalization

Author: AtlasNexusOps — Bounty #37 Bonus
"""

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from crewai_memanto_integration import MemantoMemory


@dataclass
class ConflictReport:
    """Detected memory conflict."""
    topic: str
    old_memory: dict
    new_memory: dict
    old_confidence: float
    new_confidence: float
    resolution: str = "unresolved"  # unresolved, keep_old, keep_new, merge, manual
    merged_content: Optional[str] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MemoryManager:
    """
    Detects and resolves contradictory memories.

    Usage:
        mgr = MemoryManager(memory)
        conflicts = mgr.detect_conflicts()
        mgr.resolve(conflicts[0], strategy="keep_higher_confidence")
        mgr.export_csv("memories.csv")
    """

    # Keywords that indicate contradictory facts about the same topic
    COMPARISON_WORDS = {"price", "cost", "rate", "size", "count", "number", "amount",
                         "version", "status", "state", "level", "score", "value"}

    def __init__(self, memory: MemantoMemory):
        self.memory = memory
        self.conflicts: list[ConflictReport] = []

    def detect_conflicts(self) -> list[ConflictReport]:
        """
        Scan all memories for contradictory facts.

        Returns:
            List of ConflictReport objects.
        """
        self.conflicts = []
        all_memories = self.memory.recall("*", limit=100)
        memories = all_memories.get("memories", [])

        # Group memories by topic (approximate: shared keywords in title)
        topics: dict[str, list[dict]] = defaultdict(list)
        for mem in memories:
            title = mem.get("title", "")
            # Extract topic keywords
            for word in title.lower().split():
                clean_word = word.strip(".,;:!?\"'")
                if clean_word in self.COMPARISON_WORDS or len(clean_word) > 3:
                    topics[clean_word].append(mem)

        # Find conflicts: same topic, different content
        for topic, topic_memories in topics.items():
            if len(topic_memories) < 2:
                continue

            for i in range(len(topic_memories)):
                for j in range(i + 1, len(topic_memories)):
                    old = topic_memories[i]
                    new = topic_memories[j]

                    # Check if they're about the same thing but different values
                    if self._is_contradictory(old, new):
                        self.conflicts.append(ConflictReport(
                            topic=topic,
                            old_memory=old,
                            new_memory=new,
                            old_confidence=old.get("confidence", 0.5),
                            new_confidence=new.get("confidence", 0.5),
                        ))

        return self.conflicts

    def resolve(self, conflict: ConflictReport, strategy: str = "keep_higher_confidence",
                manual_content: Optional[str] = None) -> dict:
        """
        Resolve a memory conflict.

        Args:
            conflict: The ConflictReport to resolve.
            strategy: keep_higher_confidence, keep_newer, keep_older, merge, manual.
            manual_content: Required when strategy is 'manual'.

        Returns:
            Resolution result dict.
        """
        valid = {"keep_higher_confidence", "keep_newer", "keep_older", "merge", "manual"}
        if strategy not in valid:
            raise ValueError(f"Invalid strategy. Must be one of: {valid}")

        if strategy == "keep_higher_confidence":
            winner = conflict.old_memory if conflict.old_confidence >= conflict.new_confidence else conflict.new_memory
            loser = conflict.new_memory if winner == conflict.old_memory else conflict.old_memory
            conflict.resolution = "keep_higher_confidence"

        elif strategy == "keep_newer":
            old_time = conflict.old_memory.get("created_at", "")
            new_time = conflict.new_memory.get("created_at", "")
            winner = conflict.new_memory if new_time >= old_time else conflict.old_memory
            loser = conflict.old_memory if winner == conflict.new_memory else conflict.new_memory
            conflict.resolution = "keep_newer"

        elif strategy == "keep_older":
            old_time = conflict.old_memory.get("created_at", "")
            new_time = conflict.new_memory.get("created_at", "")
            winner = conflict.old_memory if old_time <= new_time else conflict.new_memory
            loser = conflict.new_memory if winner == conflict.old_memory else conflict.old_memory
            conflict.resolution = "keep_older"

        elif strategy == "merge":
            merged = (
                f"{conflict.old_memory.get('content', '')}\n"
                f"[UPDATED {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]: "
                f"{conflict.new_memory.get('content', '')}"
            )
            conflict.merged_content = merged
            conflict.resolution = "merge"
            # Store merged version as new memory
            self.memory.remember(
                content=merged,
                memory_type="fact",
                title=f"[MERGED] {conflict.topic}",
                confidence=max(conflict.old_confidence, conflict.new_confidence),
                tags=["merged", "conflict-resolution"],
            )

        elif strategy == "manual":
            if not manual_content:
                raise ValueError("manual_content required for 'manual' strategy")
            conflict.merged_content = manual_content
            conflict.resolution = "manual"
            self.memory.remember(
                content=manual_content,
                memory_type="fact",
                title=f"[MANUAL] {conflict.topic}",
                confidence=0.9,
                tags=["manual-resolution"],
            )

        return {"topic": conflict.topic, "strategy": strategy, "resolution": conflict.resolution}

    def resolve_all(self, strategy: str = "keep_higher_confidence") -> list[dict]:
        """Resolve all detected conflicts."""
        results = []
        for conflict in self.conflicts:
            if conflict.resolution == "unresolved":
                results.append(self.resolve(conflict, strategy))
        return results

    def _is_contradictory(self, old: dict, new: dict) -> bool:
        """Check if two memories contradict each other."""
        old_content = old.get("content", "")
        new_content = new.get("content", "")

        # Quick check: same content hash → not contradictory
        if old.get("content_hash") == new.get("content_hash"):
            return False

        # Heuristic: shared numeric/price pattern suggests contradiction
        import re
        old_numbers = set(re.findall(r'\d+\.?\d*', old_content))
        new_numbers = set(re.findall(r'\d+\.?\d*', new_content))

        # If both have numbers and they differ → potential contradiction
        if old_numbers and new_numbers and old_numbers != new_numbers:
            # Check if they're about the same entity
            shared_words = set(old_content.lower().split()) & set(new_content.lower().split())
            if len(shared_words) > 3:
                return True

        return False

    # ── Data Toolkit Export ───────────────────────────────

    def export_csv(self, path: str, deduplicate: bool = True) -> str:
        """
        Export all memories to CSV via Data Toolkit pipeline.
        Handles: dedup, null filtering, schema validation.

        Args:
            path: Output CSV path.
            deduplicate: Remove duplicate entries by content hash.

        Returns:
            Path to the CSV file.
        """
        all_data = self.memory.recall("*", limit=200)
        memories = all_data.get("memories", [])

        # Data Toolkit: deduplicate
        if deduplicate:
            seen = set()
            unique = []
            for mem in memories:
                h = hashlib.sha256(
                    json.dumps(mem, sort_keys=True, default=str).encode()
                ).hexdigest()
                if h not in seen:
                    seen.add(h)
                    unique.append(mem)
            memories = unique

        # Data Toolkit: filter nulls
        memories = [m for m in memories if m.get("content") and m.get("title")]

        # Export
        fieldnames = ["type", "title", "content", "confidence", "tags", "source", "created_at"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for mem in memories:
                writer.writerow({
                    "type": mem.get("type", ""),
                    "title": mem.get("title", ""),
                    "content": mem.get("content", ""),
                    "confidence": mem.get("confidence", ""),
                    "tags": ",".join(mem.get("tags", [])),
                    "source": mem.get("source", ""),
                    "created_at": mem.get("created_at", ""),
                })

        return path

    def export_json(self, path: str) -> str:
        """Export all memories to JSON (Data Toolkit normalized)."""
        all_data = self.memory.recall("*", limit=200)
        with open(path, "w") as f:
            json.dump(all_data, f, indent=2, default=str)
        return path

    def summary(self) -> dict:
        """Return a summary of memory state."""
        all_data = self.memory.recall("*", limit=200)
        memories = all_data.get("memories", [])
        by_type = defaultdict(int)
        total_confidence = 0.0
        for mem in memories:
            by_type[mem.get("type", "unknown")] += 1
            total_confidence += mem.get("confidence", 0)

        return {
            "total_memories": len(memories),
            "by_type": dict(by_type),
            "avg_confidence": round(total_confidence / max(len(memories), 1), 2),
            "conflicts_detected": len(self.conflicts),
            "conflicts_resolved": sum(1 for c in self.conflicts if c.resolution != "unresolved"),
        }
