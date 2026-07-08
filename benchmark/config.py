"""Configuration for the benchmarking suite."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark runs."""
    
    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Benchmark parameters
    num_conversations: int = 100
    conversation_length: int = 20  # turns per conversation
    num_queries: int = 500
    warmup_runs: int = 10
    
    # Memory-specific settings
    max_context_length: int = 8192
    memory_retrieval_limit: int = 10
    
    # Metrics
    track_latency: bool = True
    track_tokens: bool = True
    track_accuracy: bool = True
    
    # Output
    output_dir: str = "benchmark/results"
    save_traces: bool = False
    
    def __post_init__(self):
        if self.openai_api_key is None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.anthropic_api_key is None:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")


# Default benchmark scenarios
SCENARIOS = {
    "personal_preferences": {
        "description": "Track evolving user preferences over multiple sessions",
        "complexity": "medium",
        "memory_depth": "shallow",
    },
    "long_term_facts": {
        "description": "Recall facts from conversations 50+ turns ago",
        "complexity": "high",
        "memory_depth": "deep",
    },
    "multi_session_context": {
        "description": "Maintain context across multiple independent sessions",
        "complexity": "high",
        "memory_depth": "deep",
    },
    "contradiction_resolution": {
        "description": "Resolve contradictions in user statements over time",
        "complexity": "high",
        "memory_depth": "medium",
    },
    "entity_tracking": {
        "description": "Track relationships between people, places, and things",
        "complexity": "medium",
        "memory_depth": "medium",
    },
}