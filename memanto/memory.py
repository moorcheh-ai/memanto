import datetime
from typing import List, Optional, Dict, Any
from moorcheh import Moorcheh
from .query import Query

class Memory:
    def __init__(self, moorcheh: Moorcheh, memory_type: str):
        self.moorcheh = moorcheh
        self.memory_type = memory_type

    def _fetch_all_memories(self, skip_ttl_filter: bool = False) -> List[Dict[str, Any]]:
        """Fetch all memories of the given type, optionally skipping TTL filter."""
        query = Query(self.moorcheh)
        memories = query.search(f"#memory_type:{self.memory_type}")

        if not skip_ttl_filter:
            now = datetime.datetime.now()
            memories = [m for m in memories if m.get('expires_at') is None or m['expires_at'] > now]

        return memories

    def search_as_of(self, date: datetime.datetime) -> List[Dict[str, Any]]:
        """Search for memories as they existed at a specific point in time."""
        memories = self._fetch_all_memories(skip_ttl_filter=True)
        return [m for m in memories if m['created_at'] <= date]

    def search_changed_since(self, date: datetime.datetime) -> List[Dict[str, Any]]:
        """Search for memories that have changed since a specific point in time."""
        memories = self._fetch_all_memories(skip_ttl_filter=True)
        return [m for m in memories if m['updated_at'] > date]

    def search_recent(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Search for memories created or updated in the last N hours."""
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        memories = self._fetch_all_memories(skip_ttl_filter=True)
        return [m for m in memories if m['updated_at'] > cutoff]

    def get_memory(self, memory_id: str, include_expired: bool = False) -> Dict[str, Any]:
        """Get a specific memory by ID, optionally including expired memories."""
        query = Query(self.moorcheh)
        memory = query.get(memory_id)

        if memory is None:
            raise ValueError("Memory not found")

        if not include_expired and memory.get('expires_at') is not None and memory['expires_at'] < datetime.datetime.now():
            raise ValueError("Memory not found")

        return memory

    def update_memory(self, memory_id: str, content: str, expires_at: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """Update a memory, including expired memories."""
        memory = self.get_memory(memory_id, include_expired=True)
        memory['content'] = content
        memory['expires_at'] = expires_at
        memory['updated_at'] = datetime.datetime.now()

        self.moorcheh.update(memory_id, memory)
        return memory