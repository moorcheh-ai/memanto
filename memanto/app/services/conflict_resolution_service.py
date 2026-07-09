"""
Conflict Resolution Service

Detects when a newly-stored memory is a competing claim about the same
thing as an existing *active* memory of the same type, and marks the
older one superseded instead of letting both sit there indefinitely as
equally-valid facts.

This is a similarity-based heuristic, not full semantic contradiction
detection ("blue" vs. "red" isn't understood as a contradiction, per se -
it's understood as "another high-confidence preference memory about the
same subject just got written, so the previous one is presumably stale
now"). That matches the "new facts always outrank older, outdated ones"
freshness behavior Memanto already advertises, and it avoids adding an
LLM call to every single write. A stricter mode that actually asks a
model "do these two memories conflict?" before superseding anything
would catch more subtle cases and could be layered on top of this later,
gated behind its own setting, for teams that want the extra precision at
the cost of write latency.
"""

import logging
from typing import Any

from memanto.app.config import settings
from memanto.app.core import MemoryRecord

logger = logging.getLogger(__name__)


class ConflictResolutionService:
    def __init__(self, moorcheh_client):
        self.client = moorcheh_client

    def find_conflicts(self, memory: MemoryRecord) -> list[dict[str, Any]]:
        """Return existing active memories this one likely supersedes."""
        try:
            search_results = self.client.similarity_search.query(
                query=memory.content,
                namespaces=[memory.namespace()],
                top_k=10,
            )
        except Exception as e:
            # Conflict detection failing should never block the write itself.
            logger.warning(f"Conflict search failed for memory {memory.id}: {e}")
            return []

        conflicts = []
        for result in search_results.get("results", []):
            if result.get("id") == memory.id:
                continue

            metadata = result.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            def field(name: str, _result=result, _metadata=metadata):
                if name in _metadata and _metadata[name] is not None:
                    return _metadata[name]
                return _result.get(name)

            if field("memory_type") != memory.type:
                continue
            # Anything already superseded/deleted isn't a live conflict.
            if field("status") not in (None, "active"):
                continue

            score = result.get("score", 0.0)
            if score >= settings.CONFLICT_SIMILARITY_THRESHOLD:
                conflicts.append(result)

        return conflicts

    def supersede(
        self,
        conflicts: list[dict[str, Any]],
        new_memory_id: str,
        namespace: str,
        write_service,
    ) -> list[str]:
        """
        Mark each conflicting memory as superseded by the new one.

        Best-effort on purpose: the new memory has already been written
        by the time this runs, so a failure to update an old, conflicting
        memory shouldn't roll back or fail the new write - it just means
        that one old memory didn't get flagged and will need to be caught
        on a later pass.
        """
        superseded_ids = []
        for conflict in conflicts:
            old_id = conflict.get("id")
            if not old_id:
                continue
            try:
                write_service.update_memory(
                    memory_id=old_id,
                    namespace=namespace,
                    updates={"status": "superseded", "superseded_by": new_memory_id},
                )
                superseded_ids.append(old_id)
            except Exception as e:
                logger.warning(f"Failed to mark memory {old_id} as superseded: {e}")

        return superseded_ids
