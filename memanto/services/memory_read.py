import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MemoryReadService:
    # ... existing code ...

    def _apply_temporal_filter(
        self,
        memories: List[Dict],
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
    ) -> List[Dict]:
        """
        Apply temporal filtering to memories based on creation time.

        Args:
            memories: List of memory dictionaries
            created_after: ISO 8601 timestamp string (inclusive)
            created_before: ISO 8601 timestamp string (inclusive)

        Returns:
            Filtered list of memories

        Raises:
            ValueError: If timestamp boundaries are malformed
        """
        filtered_memories = []

        # Parse and validate boundaries first
        after_dt = None
        before_dt = None

        if created_after is not None:
            try:
                after_dt = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid created_after timestamp: {created_after}")
                raise ValueError(f"Invalid created_after timestamp: {created_after}") from e

        if created_before is not None:
            try:
                before_dt = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid created_before timestamp: {created_before}")
                raise ValueError(f"Invalid created_before timestamp: {created_before}") from e

        for memory in memories:
            try:
                memory_dt = datetime.fromisoformat(memory['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError, KeyError):
                logger.warning(f"Skipping memory with invalid timestamp: {memory.get('id')}")
                continue

            if after_dt is not None and memory_dt < after_dt:
                continue
            if before_dt is not None and memory_dt > before_dt:
                continue

            filtered_memories.append(memory)

        return filtered_memories