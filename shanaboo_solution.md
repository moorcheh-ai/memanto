 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love!
+
+A companion memory agent that lets your agents focus and improve while you
+keep ownership of everything they learn.
+"""
+
+__version__ = "0.1.0"
+
+from memanto.core.memory import Memory
+from memanto.core.agent import Agent
+from memanto.core.session import Session
+
+__all__ = ["Memory", "Agent", "Session"]
+
+--- /dev/null
+++ b/memanto/core/__init__.py
@@ -0,0 +1,1 @@
+"""Core Memanto package modules."""
--- a/memanto/core/memory.py
+++ b/memanto/core/memory.py
@@ -0,0 +1,247 @@
+"""Core memory management with timeline tracking and contradiction resolution."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import time
+from dataclasses import dataclass, field
+from typing import Any, Optional
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry with timeline and source tracking."""
+    
+    content: str
+    timestamp: float
+    source: str
+    confidence: float = 1.0
+    entry_id: str = field(default_factory=lambda: "")
+    contradictions: list[str] = field(default_factory=list)
+    superseded_by: Optional[str] = None
+    
+    def __post_init__(self):
+        if not self.entry_id:
+            self.entry_id = hashlib.sha256(
+                f"{self.content}:{self.timestamp}:{self.source}".encode()
+            ).hexdigest()[:16]
+
+
+class ContradictionResolver:
+    """Resolves contradictions between memory entries with timeline awareness."""
+    
+    def __init__(self):
+        self.resolution_strategies = {
+            "temporal_override": self._temporal_override,
+            "confidence_override": self._confidence_override,
+            "merge": self._merge_entries,
+        }
+    
+    def resolve(
+        self,
+        old_entry: MemoryEntry,
+        new_entry: MemoryEntry,
+        strategy: str = "temporal_override",
+    ) -> tuple[MemoryEntry, MemoryEntry]:
+        """Resolve contradiction between two entries.
+        
+        Returns:
+            Tuple of (superseded_entry, active_entry)
+        """
+        if strategy not in self.resolution_strategies:
+            strategy = "temporal_override"
+        
+        return self.resolution_strategies[strategy](old_entry, new_entry)
+    
+    def _temporal_override(
+        self, old_entry: MemoryEntry, new_entry: MemoryEntry
+    ) -> tuple[MemoryEntry, MemoryEntry]:
+        """Newer entry wins by default."""
+        if new_entry.timestamp >= old_entry.timestamp:
+            old_entry.superseded_by = new_entry.entry_id
+            new_entry.contradictions.append(old_entry.entry_id)
+            return old_entry, new_entry
+        else:
+            new_entry.superseded_by = old_entry.entry_id
+            old_entry.contradictions.append(new_entry.entry_id)
+            return new_entry, old_entry
+    
+    def _confidence_override(
+        self, old_entry: MemoryEntry, new_entry: MemoryEntry
+    ) -> tuple[MemoryEntry, MemoryEntry]:
+        """Higher confidence entry wins."""
+        if new_entry.confidence >= old_entry.confidence:
+            old_entry.superseded_by = new_entry.entry_id
+            new_entry.contradictions.append(old_entry.entry_id)
+            return old_entry, new_entry
+        else:
+            new_entry.superseded_by = old_entry.entry_id
+            old_entry.contradictions.append(new_entry.entry_id)
+            return new_entry, old_entry
+    
+    def _merge_entries(
+        self, old_entry: MemoryEntry, new_entry: MemoryEntry
+    ) -> tuple[MemoryEntry, MemoryEntry]:
+        """Merge entries, keeping both with temporal ordering."""
+        # Both entries remain active but track each other
+        old_entry.contradictions.append(new_entry.entry_id)
+        new_entry.contradictions.append(old_entry.entry_id)
+        return old_entry, new_entry
+
+
+class Memory:
+    """Core memory class with retrieval, timeline tracking, and contradiction handling."""
+    
+    def __init__(self, max_entries: int = 10000):
+        self.entries: dict[str, MemoryEntry] = {}
+        self.max_entries = max_entries
+        self._contradiction_resolver = ContradictionResolver()
+        self._access_times: dict[str, float] = {}
+    
+    def add(
+        self,
+        content: str,
+        source: str = "unknown",
+        timestamp: Optional[float] = None,
+        confidence: float = 1.0,
+        check_contradictions: bool = True,
+    ) -> MemoryEntry:
+        """Add a new memory entry with optional contradiction detection."""
+        entry = MemoryEntry(
+            content=content,
+            timestamp=timestamp or time.time(),
+            source=source,
+            confidence=confidence,
+        )
+        
+        # Check for contradictions with existing entries
+        if check_contradictions:
+            for existing in list(self.entries.values()):
+                if self._is_contradiction(existing, entry):
+                    old, new = self._contradiction_resolver.resolve(existing, entry)
+                    self.entries[old.entry_id] = old
+                    entry = new
+        
+        self.entries[entry.entry_id] = entry
+        self._access_times[entry.entry_id] = time.time()
+        
+        # Evict oldest if over limit
+        if len(self.entries) > self.max_entries:
+            self._evict_oldest()
+        
+        return entry
+    
+    def retrieve(
+        self,
+        query: Optional[str] = None,
+        limit: int = 10,
+        include_superseded: bool = False,
+        min_confidence: float = 0.0,
+    ) -> list[MemoryEntry]:
+        """Retrieve memories with filtering and ranking."""
+        results = []
+        
+        for entry in self.entries.values():
+            # Skip superseded entries unless explicitly requested
+            if not include_superseded and entry.superseded_by:
+                continue
+            
+            # Filter by confidence
+            if entry.confidence < min_confidence:
+                continue
+            
+            results.append(entry)
+        
+        # Sort by relevance/recency (simple implementation)
+        results.sort(key=lambda e: (e.confidence, e.timestamp), reverse=True)
+        
+        # Update