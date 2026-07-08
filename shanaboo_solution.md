 ```diff
--- /dev/null
+++ b/benchmarks/__init__.py
@@ -0,0 +1,3 @@
+"""Memanto Benchmarking Suite."""
+
+__version__ = "0.1.0"
\ No newline at end of file
--- /dev/null
+++ b	benchmarks/config.py
@@ -0,0 +1,42 @@
+"""Benchmark configuration and constants."""
+
+import os
+from dataclasses import dataclass
+from typing import Optional
+
+
+@dataclass
+class BenchmarkConfig:
+    """Configuration for benchmark runs."""
+    
+    # Dataset sizes
+    small_dataset_size: int = 100
+    medium_dataset_size: int = 1000
+    large_dataset_size: int = 10000
+    
+    # Query counts per benchmark
+    queries_per_benchmark: int = 100
+    
+    # Latency percentiles to track
+    latency_percentiles: tuple = (50, 90, 95, 99)
+    
+    # Token counting
+    tokens_per_character: float = 0.25  # Approximate
+    
+    # Concurrency settings
+    max_concurrent_requests: int = 10
+    
+    # Output
+    results_dir: str = "benchmark_results"
+    save_raw_results: bool = True
+    
+    # Framework-specific settings
+    memanto_url: str = "http://localhost:8000"
+    mem0_api_key: Optional[str] = None
+    zep_api_key: Optional[str] = None
+    
+    def __post_init__(self):
+        """Load environment variables."""
+        self.mem0_api_key = os.getenv("MEM0_API_KEY")
+        self.zep_api_key = os.getenv("ZEP_API_KEY")
+        if not os.path.exists(self.results_dir):
+            os.makedirs(self.results_dir)
\ No newline at end of file
--- /dev/null
+++ b	benchmarks/datasets.py
@@ -0,0 +1,218 @@
+"""Synthetic and real-world datasets for memory benchmarking."""
+
+import json
+import random
+import uuid
+from dataclasses import dataclass
+from datetime import datetime, timedelta
+from typing import Dict, List, Optional
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry for testing."""
+    id: str
+    content: str
+    timestamp: datetime
+    metadata: Dict
+    agent_id: str
+    session_id: str
+
+
+class SyntheticDataset:
+    """Generate synthetic memory datasets with controlled properties."""
+    
+    def __init__(self, seed: int = 42):
+        self.seed = seed
+        random.seed(seed)
+        
+    def generate_conversation_memory(
+        self,
+        num_entries: int = 1000,
+        num_agents: int = 10,
+        avg_entries_per_session: int = 20,
+        preference_ratio: float = 0.3,
+    ) -> List[MemoryEntry]:
+        """Generate realistic conversation memory entries."""
+        
+        templates = {
+            "preference": [
+                "User prefers {preference}",
+                "I like {preference}",
+                "My favorite {category} is {preference}",
+                "I always choose {preference} for {category}",
+                "I dislike {negative}",
+                "I prefer {preference} over {alternative}",
+            ],
+            "fact": [
+                "I work at {company}",
+                "I live in {city}",
+                "My name is {name}",
+                "I have {number} years of experience",
+                "I studied at {university}",
+            ],
+            "task": [
+                "Remind me to {task} at {time}",
+                "Schedule a meeting for {time}",
+                "I need to {task} by {deadline}",
+                "Don't forget to {task}",
+            ],
+        }
+        
+        preferences = [
+            ("dark mode", "UI theme", "light mode"),
+            ("Python", "programming language", "JavaScript"),
+            ("email", "communication", "phone calls"),
+            ("morning", "work time", "evening"),
+            ("concise responses", "response style", "detailed explanations"),
+        ]
+        
+        entries = []
+        base_time = datetime.now() - timedelta(days=30)
+        
+        for i in range(num_entries):
+            agent_id = f"agent_{random.randint(0, num_agents - 1)}"
+            session_id = f"session_{i // avg_entries_per_session}"
+            
+            if random.random() < preference_ratio:
+                pref, cat, alt = random.choice(preferences)
+                template = random.choice(templates["preference"])
+                content = template.format(preference=pref, category=cat, alternative=alt, negative=alt)
+                meta = {"type": "preference", "category": cat, "confidence": random.uniform(0.7, 1.0)}
+            else:
+                template = random.choice(templates["fact"] + templates["task"])
+                content = template.format(
+                    company="Acme Corp",
+                    city="San Francisco",
+                    name="Alice",
+                    number=random.randint(1, 20),
+                    university="MIT",
+                    task="review the proposal",
+                    time="3 PM",
+                    deadline="Friday",
+                )
+                meta = {"type": "fact" if "fact" in template else "task", "confidence": random.uniform(0.5, 1.0)}
+            
+            entry = MemoryEntry(
+                id=str(uuid.uuid4()),
+                content=content,
+                timestamp=base_time + timedelta(hours=i),
+                metadata=meta,
+                agent_id=agent_id,
+                session_id=session_id,
+            )
+            entries.append(entry)
+            
+        return entries
+    
+    def generate_preference_resolution_dataset(
+        self,
+        num_profiles: int = 50,
+        preferences_per_profile: int = 20,
+        contradictions_per_profile: int = 5,
+    ) -> List[MemoryEntry]:
+        """Generate dataset with explicit contradictions for testing resolution."""
+        
+        entries = []
+        base_time = datetime.now() - timedelta(days=60)
+        
+        preference_pairs = [
+            ("prefers dark mode", "prefers light mode", "UI theme"),
+            ("likes Python", "likes JavaScript", "programming language"),
+            ("prefers email", "prefers Slack", "communication"),
+            ("morning person", "night owl", "work schedule"),
+            ("concise responses", "detailed explanations", "communication style"),
+