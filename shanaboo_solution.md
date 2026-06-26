 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - A companion memory agent with persistent memory capabilities.
+
+This package provides memory management functionality for AI agents,
+ensuring long-term context retention without token bloat.
+"""
+
+__version__ = "0.1.0"
+
+from memanto.core.memory import Memory
+from memanto.core.agent import Agent
+from memanto.core.retrieval import RetrievalEngine
+
+__all__ = ["Memory", "Agent", "RetrievalEngine"]
+
+
--- /dev/null
+++ b/memanto/core/__init__.py
@@ -0,0 +1,5 @@
+"""Core Memanto package components.
+
+This module contains the core memory management, agent, and retrieval
+functionality for the Memanto system.
+"""
--- /dev/null
+++ b/memanto/core/memory.py
@@ -0,0 +1,287 @@
+"""Memory management core for Memanto.
+
+This module implements the core memory storage, retrieval, and management
+functionality. It handles memory consolidation, contradiction detection,
+and timeline tracking to prevent memory degradation and ensure accurate recall.
+"""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import time
+from collections import defaultdict
+from dataclasses import dataclass, field
+from datetime import datetime, timezone
+from enum import Enum
+from typing import Any, Optional
+
+
+class MemoryType(Enum):
+    """Types of memories that can be stored."""
+    FACT = "fact'
+    PREFERENCE = "preference'
+    EVENT = "event'
+    DECISION = 'decision'
+    CONTRADICTION = 'contradiction'
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry with metadata for tracking and retrieval."""
+    content: str
+    memory_type: MemoryType
+    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
+    confidence: float = 1.0
+    source: Optional[str] = None
+    tags: list[str] = field(default_factory=list)
+    contradicted_by: Optional[str] = None
+    supersedes: Optional[str] = None
+    access_count: int = 0
+    last_accessed: Optional[datetime] = None
+    embedding: Optional[list[float]] = None
+    
+    def __post_init__(self):
+        if self.confidence < 0 or self.confidence > 1:
+            raise ValueError("Confidence must be between 0 and 1")
+    
+    def to_dict(self) -> dict[str, Any]:
+        """Serialize memory entry to dictionary."""
+        return {
+            'content': self.content,
+            'memory_type': self.memory_type.value,
+            'timestamp': self.timestamp.isoformat(),
+            'confidence': self.confidence,
+            'source': self.source,
+            'tags': self.tags,
+            'contradicted_by': self.contradicted_by,
+            'supersedes': self.supersedes,
+            'access_count': self.access_count,
+            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
+        }
+    
+    @classmethod
+    def from_dict(cls, data: dict[str, Any]) -> 'MemoryEntry':
+        """Deserialize memory entry from dictionary."""
+        entry = cls(
+            content=data['content'],
+            memory_type=MemoryType(data['memory_type']),
+            timestamp=datetime.fromisoformat(data['timestamp']),
+            confidence=data['confidence'],
+            source=data.get('source'),
+            tags=data.get('tags', []),
+            contradicted_by=data.get('contradicted_by'),
+            supersedes=data.get('supersedes'),
+        )
+        entry.access_count = data.get('access_count', 0)
+        last_accessed = data.get('last_accessed')
+        if last_accessed:
+            entry.last_accessed = datetime.fromisoformat(last_accessed)
+        return entry
+    
+    def generate_id(self) -> str:
+        """Generate a unique ID for this memory entry."""
+        content_hash = hashlib.sha256(
+            f"{self.content}:{self.timestamp.isoformat()}".encode()
+        ).hexdigest()[:16]
+        return content_hash
+
+
+class MemoryStore:
+    """In-memory storage with persistence and retrieval capabilities."""
+    
+    def __init__(self, max_size: int = 10000):
+        self._memories: dict[str, MemoryEntry] = {}
+        self._index: dict[str, set[str]] = defaultdict(set)
+        self._timeline: list[tuple[datetime, str]] = []
+        self.max_size = max_size
+    
+    def add(self, entry: MemoryEntry) -> str:
+        """Add a memory entry to the store.
+        
+        Returns:
+            The ID of the stored memory.
+        """
+        memory_id = entry.generate_id()
+        self._memories[memory_id] = entry
+        
+        # Update index
+        for word in entry.content.lower().split():
+            self._index[word].add(memory_id)
+        for tag in entry.tags:
+            self._index[tag.lower()].add(memory_id)
+        
+        # Update timeline
+        self._timeline.append((entry.timestamp, memory_id))
+        self._timeline.sort(key=lambda x: x[0])
+        
+        # Check for contradictions
+        self._check_contradictions(memory_id)
+        
+        return memory_id
+    
+    def get(self, memory_id: str) -> Optional[MemoryEntry]:
+        """Retrieve a memory by ID and update access metrics."""
+        entry = self._memories.get(memory_id)
+        if entry:
+            entry.access_count += 1
+            entry.last_accessed = datetime.now(timezone.utc)
+        return entry
+    
+    def search(
+        self,
+        query: str,
+        memory_type: Optional[MemoryType] = None,
+        limit: int = 10,
+        min_confidence: float = 0.0,
+    ) -> list[tuple[str, MemoryEntry, float]]:
+        """Search for memories matching the query.
+        
+        Returns:
+            List of tuples (memory_id, entry, relevance_score).
+        """
+        query_words = set(query.lower().split())
+        scores: dict[str, float] = defaultdict(float)
+        
+        for word in query_words:
+            for memory_id in self._index.get(word, set()):
+                scores[memory_id] += 1.0
+        
+        results = []
+        for memory_id, score