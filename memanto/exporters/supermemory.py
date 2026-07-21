import json
from typing import Dict, List, Set, Optional
from memanto.models import Memory
from memanto.exporters.base import BaseExporter

class SupermemoryExporter(BaseExporter):
    def __init__(self, config: Dict):
        super().__init__(config)
        self.seen_ids: Set[str] = set()
        self.tag_associations: Dict[str, List[str]] = {}

    def export_memory(self, memory: Memory) -> Optional[Dict]:
        if memory.id in self.seen_ids:
            # Update tag associations for existing memory
            if memory.id in self.tag_associations:
                self.tag_associations[memory.id].extend(memory.container_tags)
            else:
                self.tag_associations[memory.id] = memory.container_tags.copy()
            return None

        self.seen_ids.add(memory.id)
        self.tag_associations[memory.id] = memory.container_tags.copy()

        # Create export record with all tags
        export_record = {
            "id": memory.id,
            "content": memory.content,
            "container_tags": list(set(memory.container_tags)),  # Deduplicate tags
            "metadata": memory.metadata,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat()
        }

        return export_record

    def finalize_export(self) -> List[Dict]:
        # Generate per-tag buckets
        memories_by_container_tag = {}

        for memory_id, tags in self.tag_associations.items():
            for tag in tags:
                if tag not in memories_by_container_tag:
                    memories_by_container_tag[tag] = []
                # Add memory with its singular container_tag for compatibility
                memories_by_container_tag[tag].append({
                    "id": memory_id,
                    "container_tag": tag  # Legacy format
                })

        return {
            "memories": [self._get_memory_record(memory_id) for memory_id in self.seen_ids],
            "memories_by_container_tag": memories_by_container_tag
        }

    def _get_memory_record(self, memory_id: str) -> Dict:
        # This would fetch the full memory record from storage
        # Implementation depends on your storage system
        pass