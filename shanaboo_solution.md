```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love."""
+
+from memanto.core import Memanto
+from memanto.skills import SkillContext, SkillMemory
+from memanto.integrations import ContextFragmentationFixer
+
+__all__ = [
+    "Memanto",
+    "SkillContext",
+    "SkillMemory",
+    "ContextFragmentationFixer",
+]
+
+
+__version__ = "0.1.0"
\ No newline at end of file
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,180 @@
+"""Core Memanto memory agent for persistent cross-session context."""
+
+import json
+import hashlib
+import time
+from typing import Any, Dict, List, Optional, Callable
+from dataclasses import dataclass, field, asdict
+from datetime import datetime
+from pathlib import Path
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry with metadata for retrieval."""
+    content: str
+    source_skill: str
+    memory_type: str  # 'architectural', 'preference', 'quirk', 'decision', 'general'
+    timestamp: float = field(default_factory=time.time)
+    tags: List[str] = field(default_factory=list)
+    confidence: float = 1.0
+    access_count: int = 0
+    last_accessed: float = field(default_factory=time.time)
+    
+    def to_dict(self) -> Dict[str, Any]:
+        return asdict(self)
+    
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
+        return cls(**data)
+    
+    def bump_access(self) -> None:
+        self.access_count += 1
+        self.last_accessed = time.time()
+
+
+class Memanto:
+    """
+    Active memory companion that listens to skill inputs/outputs,
+    distills context, and injects relevant memories into prompts.
+    """
+    
+    def __init__(
+        self,
+        storage_path: Optional[str] = None,
+        max_memories_per_query: int = 10,
+        relevance_threshold: float = 0.5,
+    ):
+        self.storage_path = Path(storage_path) if storage_path else Path.home() / ".memanto" / "memory.json"
+        self.max_memories_per_query = max_memories_per_query
+        self.relevance_threshold = relevance_threshold
+        self._memories: List[MemoryEntry] = []
+        self._listeners: List[Callable] = []
+        self._load()
+    
+    def _load(self) -> None:
+        """Load persisted memories from disk."""
+        if self.storage_path.exists():
+            try:
+                data = json.loads(self.storage_path.read_text())
+                self._memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]
+            except (json.JSONDecodeError, KeyError, TypeError):
+                self._memories = []
+        else:
+            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
+    
+    def _save(self) -> None:
+        """Persist memories to disk."""
+        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
+        data = {
+            "version": "1.0",
+            "last_updated": time.time(),
+            "memories": [m.to_dict() for m in self._memories],
+        }
+        self.storage_path.write_text(json.dumps(data, indent=2, default=str))
+    
+    def remember(
+        self,
+        content: str,
+        source_skill: str,
+        memory_type: str = "general",
+        tags: Optional[List[str]] = None,
+    ) -> MemoryEntry:
+        """
+        Actively listen and store a distilled memory from skill execution.
+        """
+        entry = MemoryEntry(
+            content=content,
+            source_skill=source_skill,
+            memory_type=memory_type,
+            tags=tags or [],
+        )
+        self._memories.append(entry)
+        self._save()
+        self._notify_listeners("remember", entry)
+        return entry
+    
+    def recall(
+        self,
+        query: str,
+        skill_filter: Optional[str] = None,
+        memory_type: Optional[str] = None,
+        top_k: Optional[int] = None,
+    ) -> List[MemoryEntry]:
+        """
+        Recall relevant memories based on query with simple relevance scoring.
+        """
+        max_results = top_k or self.max_memories_per_query
+        scored = []
+        
+        for memory in self._memories:
+            # Filter by skill if specified
+            if skill_filter and memory.source_skill != skill_filter:
+                continue
+            if memory_type and memory.memory_type != memory_type:
+                continue
+            
+            # Simple relevance: keyword overlap + recency + access frequency
+            score = self._compute_relevance(query, memory)
+            if score >= self.relevance_threshold:
+                scored.append((score, memory))
+        
+        # Sort by score descending
+        scored.sort(key=lambda x: x[0], reverse=True)
+        
+        results = []
+        for score, memory in scored[:max_results]:
+            memory.bump_access()
+            results.append(memory)
+        
+        self._save()
+        return results
+    
+    def _compute_relevance(self, query: str, memory: MemoryEntry) -> float:
+        """Compute relevance score between query and memory."""
+        query_lower = query.lower()
+        content_lower = memory.content.lower()
+        
+        # Keyword overlap
+        query_words = set(query_lower.split())
+        content_words = set(content_lower.split())
+        if not query_words:
+            return 0.0
+        
+        overlap = len(query_words & content_words) / len(query_words)
+        
+        # Recency boost (exponential decay over 30 days)
+        age_days = (time.time() - memory.timestamp) / 86400
+        recency_boost = max(0, 1 - (age_days / 30)) * 0.3
+        
+        # Access frequency boost
+        freq_boost = min(memory.access_count / 10, 0.2)
+        
+        return min(overlap + recency_boost + freq_boost, 1.0)
+    
+    def answer(self, query: str) -> str:
+        """
+        Answer a query by recalling and synthesizing relevant memories.
+        """
+        memories =