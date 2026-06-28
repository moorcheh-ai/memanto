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
+
+--- a/memanto/core/memory.py
+++ b/memanto/core/memory.py
@@ -0,0 +1,247 @@
+"""Core memory management with timeline tracking and contradiction resolution."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import re
+from dataclasses import dataclass, field
+from datetime import datetime, timezone
+from typing import Any, Optional
+
+
+@dataclass
+class MemoryFact:
+    """A single memory fact with metadata for timeline and source tracking."""
+    
+    content: str
+    timestamp: datetime
+    source: str
+    fact_id: str = field(default_factory=lambda: "")
+    confidence: float = 1.0
+    contradicted_by: Optional[str] = None
+    is_contradiction: bool = False
+    version: int = 1
+    
+    def __post_init__(self):
+        if not self.fact_id:
+            self.fact 
+
+
+class ContradictionResolver:
+    """Resolves contradictions between memory facts with proper timeline tracking."""
+    
+    CONTRADICTION_PATTERNS = [
+        # Pattern: "X is Y" vs "X is not Y" / "X is Z"
+        (r"(?i)(.+)\s+is\s+(.+)", r"\1\s+is\s+(not\s+)?(?!\\2\b).+"),
+        # Pattern: "always X" vs "never X" / "sometimes X"
+        (r"(?i)always\s+(.+)", r"(never|sometimes|no longer)\s+\1"),
+        # Pattern: "use X" vs "don't use X" / "use Y instead"
+        (r"(?i)use\s+(.+)", r"(don't|do not|never)\s+use\s+\1"),
+        # Pattern: "prefer X" vs "prefer Y" (different objects)
+        (r"(?i)prefer\s+(.+)", r"prefer\s+(?!\\1\b).+"),
+    ]
+    
+    @classmethod
+    def detect_contradiction(cls, fact1: MemoryFact, fact2: MemoryFact) -> bool:
+        """Detect if two facts contradict each other."""
+        # Same fact can't contradict itself
+        if fact1.fact_id == fact2.fact_id:
+            return False
+        
+        # Normalize content for comparison
+        content1 = cls._normalize(fact1.content)
+        content2 = cls._normalize(fact2.content)
+        
+        # Check for direct negation patterns
+        for pattern, negation in cls.CONTRADICTION_PATTERNS:
+            if re.search(pattern, content1) and re.search(negation, content2):
+                if cls._same_subject(content1, content2):
+                    return True
+            if re.search(pattern, content2) and re.search(negation, content1):
+                if cls._same_subject(content1, content2):
+                    return True
+        
+        # Check for temporal contradictions (same subject, different values)
+        if cls._same_subject(content1, content2) and cls._different_predicate(content1, content2):
+            # Check if they have overlapping semantic meaning
+            similarity = cls._semantic_similarity(content1, content2)
+            if similarity > 0.7:  # High semantic overlap suggests potential contradiction
+                return True
+        
+        return False
+    
+    @staticmethod
+    def _normalize(content: str) -> str:
+        """Normalize content for comparison."""
+        content = content.lower().strip()
+        # Remove extra whitespace
+        content = re.sub(r'\s+', ' ', content)
+        return content
+    
+    @staticmethod
+    def _same_subject(content1: str, content2: str) -> bool:
+        """Check if two facts are about the same subject."""
+        # Extract subject (first noun phrase or first few words)
+        words1 = content1.split()[:3]
+        words2 = content2.split()[:3]
+        # Simple heuristic: share at least 2 of first 3 significant words
+        shared = sum(1 for w in words1 if w in words2 and len(w) > 2)
+        return shared >= 1
+    
+    @staticmethod
+    def _different_predicate(content1: str, content2: str) -> bool:
+        """Check if two facts have different predicates/values."""
+        # Simple check: are they different statements?
+        return content1 != content2
+    
+    @staticmethod
+    def _semantic_similarity(content1: str, content2: str) -> float:
+        """Calculate simple semantic similarity between two strings."""
+        # Jaccard similarity on word sets
+        words1 = set(content1.split())
+        words2 = set(content2.split())
+        if not words1 or not words2:
+            return 0.0
+        intersection = words1 & words2
+        union = words1 | words2
+        return len(intersection) / len(union)
+    
+    @classmethod
+    def resolve(cls, old_fact: MemoryFact, new_fact: MemoryFact) -> MemoryFact:
+        """Resolve contradiction by keeping the newer fact with proper attribution."""
+        # The newer fact supersedes the old one
+        new_fact.is_contradiction = True
+        new_fact.version = old_fact.version + 1
+        return new_fact
+
+
+class MemoryStore:
+    """Secure memory store with timeline tracking and contradiction handling."""
+    
+    def __init__(self):
+        self._facts: dict[str, MemoryFact] = {}
+        self._timeline_index: list[tuple[datetime, str]] = []  # (timestamp, fact_id)
+        self._contradiction_resolver = ContradictionResolver()
+    
+    def add_fact(self, content: str, source: str, timestamp: Optional[datetime] = None) -> MemoryFact:
+        """Add a fact to memory with automatic contradiction detection."""
+        if not content or not content.strip():
+            raise ValueError("Fact content cannot be empty