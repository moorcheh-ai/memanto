"""Dataset registry — auto-discovered by run.py."""

from .agent_memory_bench import AgentMemoryBenchDataset
from .locomo import LoCoMoDataset
from .memoryagentbench import MemoryAgentBenchDataset

DATASETS: dict[str, type] = {
    "locomo": LoCoMoDataset,
    "longmemeval": LoCoMoDataset,  # alias
    "memoryagentbench": MemoryAgentBenchDataset,
    "agentmemorybench": AgentMemoryBenchDataset,
}

__all__ = [
    "DATASETS",
    "LoCoMoDataset",
    "MemoryAgentBenchDataset",
    "AgentMemoryBenchDataset",
]
