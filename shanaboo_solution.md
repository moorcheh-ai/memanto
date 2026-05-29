```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,6 @@
+"""Memanto - Memory that AI Agents Love."""
+
+from memanto.core import Memanto
+from memanto.skills import SkillIntegration
+
+__all__ = ["Memanto", "SkillIntegration"]
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,0 @@
+"""Core Memanto memory agent implementation."""
+
+import json
+import hashlib
+from datetime import datetime
+from pathlib import Path
+from typing import Any, Dict, List, Optional, Callable
+from dataclasses import dataclass, asdict
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry with metadata for retrieval and relevance scoring."""
+    
+    content: str
+    source_skill: str
+    memory_type: str  # e.g., 'architectural_decision', 'coding_preference', 'codebase_quirk'
+    timestamp: str
+    session_id: Optional[str] = None
+    tags: Optional[List[str]] = None
+    relevance_score: float = 0.0
+    access_count: int = 0
+    last_accessed: Optional[str] = None
+    
+    def to_dict(self) -> Dict[str, Any]:
+        return asdict(self)
+    
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
+        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
+
+
+class MemantoStore:
+    """Persistent storage backend for Memanto memories."""
+    
+    def __init__(self, storage_path: Optional[str] = None):
+        self.storage_path = Path(storage_path or "~/.memanto/memories.json").expanduser()
+        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
+        self._memories: List[MemoryEntry] = []
+        self._load()
+    
+    def _load(self) -> None:
+        """Load memories from persistent storage."""
+        if self.storage_path.exists():
+            try:
+                data = json.loads(self.storage_path.read_text())
+                self._memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]
+            except (json.JSONDecodeError, KeyError, TypeError):
+                self._memories = []
+        else:
+            self._memories = []
+    
+    def _save(self) -> None:
+        """Persist memories to storage."""
+        data = {
+            "version": "1.0",
+            "last_updated": datetime.now().isoformat(),
+            "memories": [m.to_dict() for m in self._memories]
+        }
+        self.storage_path.write_text(json.dumps(data, indent=2, default=str))
+    
+    def add(self, entry: MemoryEntry) -> None:
+        """Add a new memory entry."""
+        self._memories.append(entry)
+        self._save()
+    
+    def query(
+        self,
+        skill_context: str,
+        memory_types: Optional[List[str]] = None,
+        limit: int = 10,
+        min_relevance: float = 0.0
+    ) -> List[MemoryEntry]:
+        """
+        Query memories relevant to the current skill context.
+        Simple keyword-based relevance scoring for MVP.
+        """
+        skill_context_lower = skill_context.lower()
+        scored = []
+        
+        for memory in self._memories:
+            if memory_types and memory.memory_type not in memory_types:
+                continue
+            
+            # Simple relevance: keyword overlap
+            content_lower = memory.content.lower()
+            skill_words = set(skill_context_lower.split())
+            content_words = set(content_lower.split())
+            overlap = skill_words & content_words
+            
+            if overlap:
+                relevance = len(overlap) / max(len(skill_words), 1)
+            else:
+                relevance = 0.0
+            
+            # Boost recently accessed memories
+            if memory.last_accessed:
+                try:
+                    last_access = datetime.fromisoformat(memory.last_accessed)
+                    days_since = (datetime.now() - last_access).days
+                    relevance += max(0, 0.1 - days_since * 0.001)  # Small decay factor
+                except ValueError:
+                    pass
+            
+            # Boost frequently accessed memories
+            relevance += min(memory.access_count * 0.01, 0.1)
+            
+            if relevance >= min_relevance:
+                memory.relevance_score = relevance
+                scored.append((relevance, memory))
+        
+        # Sort by relevance descending
+        scored.sort(key=lambda x: x[0], reverse=True)
+        results = [m for _, m in scored[:limit]]
+        
+        # Update access metadata
+        for memory in results:
+            memory.access_count += 1
+            memory.last_accessed = datetime.now().isoformat()
+        
+        self._save()
+        return results
+    
+    def get_all(self) -> List[MemoryEntry]:
+        """Return all stored memories."""
+        return self._memories.copy()
+    
+    def clear(self) -> None:
+        """Clear all memories."""
+        self._memories = []
+        self._save()
+
+
+class Memanto:
+    """
+    Active memory companion that persists context across skill executions.
+    
+    Memanto listens to skill inputs/outputs, distills architectural decisions,
+    coding preferences, and codebase quirks, then injects relevant context
+    into subsequent skill executions.
+    """
+    
+    def __init__(self, storage_path: Optional[str] = None):
+        self.store = MemantoStore(storage_path)
+        self._session_id: Optional[str] = None
+    
+    @property
+    def session_id(self) -> Optional[str]:
+        return self._session_id
+    
+    @session_id.setter
+    def session_id(self, value: str) -> None:
+        self._session_id = value
+    
+    def remember(
+        self,
+        content: str,
+        source_skill: str,
+        memory_type: str = "general",
+        tags: Optional[List[str]] = None
+    ) -> MemoryEntry:
+        """
+        Actively store a distilled memory from skill execution.
+        
+        Args:
+            content: The distilled memory content
+            source_skill: Which skill produced this memory
+            memory_type: Category of memory (architectural_decision, coding_preference, etc.)
+            tags: Optional tags for