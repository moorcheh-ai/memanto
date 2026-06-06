"""Base scenario class for memory benchmarking."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class ScenarioResult:
    """Results from running a benchmark scenario."""
    
    scenario_name: str
    adapter_name: str
    success: bool
    accuracy_score: float = 0.0
    latency_ms: float = 0.0
    tokens_used: int = 0
    memory_footprint_mb: float = 0.0
    recall_precision: float = 0.0
    recall_recall: float = 0.0
    recall_f1: float = 0.0
    context_window_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "adapter_name": self.adapter_name,
            "success": self.success,
            "accuracy_score": self.accuracy_score,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "memory_footprint_mb": self.memory_footprint_mb,
            "recall_precision": self.recall_precision,
            "recall_recall": self.recall_recall,
            "recall_f1": self.recall_f1,
            "context_window_tokens": self.context_window_tokens,
            "metadata": self.metadata,
            "errors": self.errors,
        }


class BaseScenario(ABC):
    """Base class for all benchmark scenarios."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._ground_truth: List[Dict[str, Any]] = []
        self._interactions: List[Dict[str, Any]] = []
    
    @property
    def ground_truth(self) -> List[Dict[str, Any]]:
        """Get ground truth data for evaluation."""
        return self._ground_truth
    
    @property
    def interactions(self) -> List[Dict[str, Any]]:
        """Get interaction sequence for the scenario."""
        return self._interactions
    
    @abstractmethod
    def setup(self) -> None:
        """Initialize the scenario with test data."""
        pass
    
    @abstractmethod
    async def run(self, adapter: Any) -> ScenarioResult:
        """
        Execute the scenario against a memory adapter.
        
        Args:
            adapter: The memory system adapter to test
            
        Returns:
            ScenarioResult with performance metrics
        """
        pass
    
    @abstractmethod
    def evaluate(self, results: List[Any]) -> Dict[str, float]:
        """
        Evaluate results against ground truth.
        
        Returns:
            Dictionary of metric names to scores
        """
        pass
    
    def _calculate_f1(self, precision: float, recall: float) -> float:
        """Calculate F1 score from precision and recall."""
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)
    
    def _token_count(self, text: str) -> int:
        """
        Estimate token count for text.
        Uses rough heuristic: ~4 characters per token on average.
        """
        return len(text) // 4