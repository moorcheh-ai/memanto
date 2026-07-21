from typing import Dict, List, Optional
from memanto.models import Memory
from memanto.mappers.base import BaseMapper

class SupermemoryMapper(BaseMapper):
    def map_memory(self, memory_data: Dict) -> Optional[Memory]:
        # Handle both current container_tags array and legacy container_tag
        container_tags = memory_data.get("container_tags", [])
        if isinstance(container_tags, str):
            container_tags = [container_tags]
        elif not isinstance(container_tags, list):
            container_tags = []

        # Add legacy container_tag if present and not already in container_tags
        legacy_tag = memory_data.get("container_tag")
        if legacy_tag and legacy_tag not in container_tags:
            container_tags.append(legacy_tag)

        # Deduplicate tags
        container_tags = list(set(container_tags))

        return Memory(
            id=memory_data["id"],
            content=memory_data["content"],
            container_tags=container_tags,
            metadata=memory_data.get("metadata", {}),
            created_at=memory_data["created_at"],
            updated_at=memory_data["updated_at"]
        )