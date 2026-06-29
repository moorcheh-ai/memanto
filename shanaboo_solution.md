 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love!
+
+A companion memory agent that lets your agents focus and improve
+while you keep ownership of everything they learn.
+"""
+
+__version__ = "0.1.0"
+
+from memanto.core import (
+    Memanto,
+    MemoryConfig,
+    MemoryEntry,
+)
+
+__all__ = ["Memanto", "MemoryConfig", "MemoryEntry"]
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,287 @@
+"""Core Memanto memory management with timeline tracking and contradiction resolution."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import re
+import threading
+import time
+from dataclasses import dataclass, field
+from datetime import datetime, timezone
+from typing import Any, Callable, Optional
+
+
+@dataclass
+class MemoryConfig:
+    """Configuration for Memanto memory agent."""
+    
+    max_entries: int = 10000
+    contradiction_threshold: float = 0.85
+    timeline_resolution: str = "day"  # day, hour, minute
+    enable_source_attribution: bool = True
+    context_window_size: int = 4096
+    
+    def __post_init__(self):
+        if self.max_entries <= 0:
+            raise ValueError("max_entries must be positive")
+        if not 0 <= self.contradiction_threshold <= 1:
+            raise ValueError("contradiction_threshold must be between 0 and 1")
+
+
+@dataclass 
+class MemoryEntry:
+    """A single memory entry with metadata for timeline and source tracking."""
+    
+    content: str
+    timestamp: datetime
+    source: str
+    entry_type: str = "fact"
+    confidence: float = 1.0
+    tags: list[str] = field(default_factory=list)
+    _id: Optional[str] = None
+    _contradicts: Optional[list[str]] = None
+    
+    def __post_init__(self):
+        if self._id is None:
+            self._id = self._generate_id()
+        if self._contradicts is None:
+            self._contradicts = []
+    
+    def _generate_id(self) -> str:
+        """Generate unique ID based on content and timestamp."""
+        data = f"{self.content}:{self.timestamp.isoformat()}"
+        return hashlib.sha256(data.encode()).hexdigest()[:16]
+    
+    def to_dict(self) -> dict[str, Any]:
+        """Serialize memory entry to dictionary."""
+        return {
+            "id": self._id,
+            "content": self.content,
+            "timestamp": self.timestamp.isoformat(),
+            "source": self.source,
+            "entry_type": self.entry_type,
+            "confidence": self.confidence,
+            "tags": self.tags,
+            "contradicts": self._contradicts,
+        }
+    
+    @classmethod
+    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
+        """Deserialize memory entry from dictionary."""
+        entry = cls(
+            content=data["content"],
+            timestamp=datetime.fromisoformat(data["timestamp"]),
+            source=data["source"],
+            entry_type=data.get("entry_type", "fact"),
+            confidence=data.get("confidence", 1.0),
+            tags=data.get("tags", []),
+        )
+        entry._id = data["id"]
+        entry._contradicts = data.get("contradicts", [])
+        return entry
+
+
+class ContradictionResolver:
+    """Handles detection and resolution of contradictory memories."""
+    
+    # Common contradiction patterns
+    CONTRADICTION_PATTERNS = [
+        (r"\b(is|are|was|were)\s+(\w+)", r"\1\s+not\s+\2"),  # X is Y vs X is not Y
+        (r"\b(never|always|sometimes)\b", r"\b(always|never|sometimes)\b"),  # frequency
+        (r"\b(love|hate|like|dislike)\b", r"\b(hate|love|dislike|like)\b"),  # preference
+        (r"(\d+)\s*(kg|lbs|pounds|kilograms)", r"(\d+)\s*(kg|lbs|pounds|kilograms)"),  # measurements
+    ]
+    
+    def __init__(self, threshold: float = 0.85):
+        self.threshold = threshold
+        self._lock = threading.RLock()
+    
+    def calculate_similarity(self, text1: str, text2: str) -> float:
+        """Calculate semantic similarity between two texts using simple word overlap."""
+        # Normalize texts
+        words1 = set(re.findall(r'\b\w+\b', text1.lower()))
+        words2 = set(re.findall(r'\b\w+\b', text2.lower()))
+        
+        if not words1 or not words2:
+            return 0.0
+        
+        # Jaccard similarity
+        intersection = words1 & words2
+        union = words1 | words2
+        return len(intersection) / len(union)
+    
+    def detect_contradiction(self, entry1: MemoryEntry, entry2: MemoryEntry) -> bool:
+        """Detect if two entries contradict each other."""
+        with self._lock:
+            similarity = self.calculate_similarity(entry1.content, entry2.content)
+            
+            # High similarity but different key terms suggests contradiction
+            if similarity < 0.3:  # Too different, not a contradiction
+                return False
+            
+            # Check for explicit negation patterns
+            text1_lower = entry1.content.lower()
+            text2_lower = entry2.content.lower()
+            
+            # Direct negation check
+            negation_indicators = ["not ", "no longer", "never", "don't", "doesn't", "didn't"]
+            has_negation_1 = any(ind in text1_lower for ind in negation_indicators)
+            has_negation_2 = any(ind in text2_lower for ind in negation_indicators)
+            
+            # If one has negation and other doesn't, and they're similar, likely contradiction
+            if has_negation_1 != has_negation_2 and similarity > self.threshold:
+                return True
+            
+            # Check for antonym patterns
+            antonym_pairs = [
+                ("love", "hate"), ("like", "